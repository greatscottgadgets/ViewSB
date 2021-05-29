"""
Rhododendron backend for ViewSB.

This file is part of ViewSB.
"""

# pylint: disable=maybe-no-member,access-member-before-definition

import os
import array
import errno

from datetime import datetime, timedelta

import crcmod

from ..backend import ViewSBBackend
from ..packet import USBPacket


# Default sample-delivery timeout.
SAMPLE_DELIVERY_TIMEOUT_MS  = 100

# Speed constants.
SPEED_HIGH = 0
SPEED_FULL = 1
SPEED_LOW  = 2

# Speed name constants.
SPEED_NAMES = {
    SPEED_HIGH: 'high',
    SPEED_FULL: 'full',
    SPEED_LOW:  'low',
}


try:
    import greatfet

    # FIXME: move to GreatFET?
    def read_rhododendron_m0_loadable():
        """ Read the contents of the default Rhododendron loadable from the tools distribution. """

        RHODODENDRON_M0_FILENAME = 'rhododendron_m0.bin'

        filename = os.getenv('RHODODENDRON_M0_BIN', RHODODENDRON_M0_FILENAME)

        # If we haven't found another path, fall back to an m0 binary in the current directory.
        if filename is None:
            filename = RHODODENDRON_M0_FILENAME

        with open(filename, 'rb') as f:
            return f.read()


except (ImportError, ModuleNotFoundError) as e:
    pass


class USBHackDelineator:
    """
    Class that breaks a USB data stream into its component parts.

    This -hack- version works without delineation packets using a (very good) parsing heuristic.
    It'll work well enough for 99% of cases; and it'll be replaced once that 1% bites me hard enough
    that I wind up coming back around to this.
    """

    # Polynomial used for the USB CRC16.
    USB_CRC_POLYNOMIAL = 0x18005

    inner_data_crc = staticmethod(crcmod.mkCrcFun(USB_CRC_POLYNOMIAL))

    @classmethod
    def data_crc(cls, data):
        return cls.inner_data_crc(data) ^ 0xFFFF


    def __init__(self, backend):

        self.backend = backend

        # Create holding buffers for our "packet boundary" data and for our
        # data pending packetization.
        self.pending_data = []


    def submit_data(self, data):

        # Add our new data to our list of pending data...
        self.pending_data.extend(data)

        # ... and check to see if we can break it into packets.
        self.divine_boundaries()


    @staticmethod
    def is_valid_pid(byte):

        pid_low = byte & 0x0f
        pid_high = byte >> 4
        pid_high_inverse = pid_high ^ 0xf

        return pid_low == pid_high_inverse


    def divine_boundaries(self):
        TOKEN_LENGTH         = 3
        HANDSHAKE_LENGTH     = 1

        TOKEN_PID_SUFFIX     = 0b01
        HANDSHAKE_PID_SUFFIX = 0b10
        DATA_PID_SUFFIX      = 0b11
        SPECIAL_PID_SUFFIX   = 0b00


        while self.pending_data:

            # Grab the first byte of our data, which should be our USB packet ID.
            pid = self.pending_data[0]

            # If this packet isn't a valid PID, it doesn't start a USB packet. Skip it.
            if not self.is_valid_pid(pid):
                del self.pending_data[0]
                continue

            # Extract the last two bits of the PID, which tell us what category
            # of packet this is.
            pid_suffix = pid & 0b11

            # If this is a TOKEN pid, we always have three bytes of data.
            if pid_suffix == TOKEN_PID_SUFFIX:
                if len(self.pending_data) < TOKEN_LENGTH:
                    return

                packet = self.pending_data[0:TOKEN_LENGTH]
                del self.pending_data[0:TOKEN_LENGTH]

                self.emit_packet(packet)

            # If this is a handshake packet, we always have just the PID of data.
            elif pid_suffix == HANDSHAKE_PID_SUFFIX:
                del self.pending_data[0]
                self.emit_packet([pid])


            # If this is a handshake packet, we always have just the PID of data.
            elif pid_suffix == SPECIAL_PID_SUFFIX:
                del self.pending_data[0]
                self.emit_packet([pid])


            # If this is a DATA pid, we'll need to try various lengths to see if anything matches our framing format.
            elif (pid_suffix == DATA_PID_SUFFIX) & (len(self.pending_data) >= 3):

                # Try every currently possible packet length.
                for length in range(3, 515):

                    if length > len(self.pending_data):
                        return

                    # Extract the payload of the given packet, and compute its CRC.
                    payload = bytes(self.pending_data[1:length-2])
                    payload_crc = self.data_crc(payload)

                    # Read the end of the theoretical packet, and parse it as a CRC.
                    packet_crc = self.pending_data[length-2] | (self.pending_data[length-1] << 8)

                    # If they match, odds are this is the end of the data packet.
                    if payload_crc == packet_crc:
                        packet = self.pending_data[0:length]
                        del self.pending_data[0:length]

                        self.emit_packet(packet)


    def emit_packet(self, data):
        """ Submits a given packet to our output driver for processing. """

        # Convert the data to a USBPacket.
        timestamp = self.backend.get_microseconds()
        packet = USBPacket.from_raw_packet(
            bytearray(data),
            timestamp=timedelta(microseconds=timestamp)
        )

        # Submit the delineated packet to our backend.
        self.backend.emit_packet(packet)




class Rhododendron(ViewSBBackend):
    """ Capture backend that captures packets from a GreatFET Rhododendron. """

    UI_NAME = "rhododendron"
    UI_DESCRIPTION = "GreatFET Rhododendron capture neighbor"

    SPEEDS = {
        'high': SPEED_HIGH,
        'full': SPEED_FULL,
        'low':  SPEED_LOW,
    }

    @staticmethod
    def reason_to_be_disabled():
        # The main reason we'd not be available would be that pyopenvizsla
        # isn't importable (and thus likely not installed).

        if not 'find_greatfet_asset' in globals():
            return "greatfet python module not available"

        try:
            read_rhododendron_m0_loadable()
        except IOError:
            return "rhododendron loadable not found"

        return None


    @classmethod
    def speed_from_string(cls, string):

        try:
            return cls.SPEEDS[string]
        except KeyError:
            return None


    @classmethod
    def add_options(cls, parser):

        parser.add_argument('--speed', dest='capture_speed', default='high', choices=cls.SPEEDS.keys(),
            help="The speed of the USB data to capture.")


    def __init__(self, capture_speed, suppress_packet_callback=None):
        """ Creates a new Rhododendron capture backend.

        Args:
            capture_speed -- The speed at which to capture.
            suppress_packet_callback -- A callback function that determines
                which packets should be dropped before being submitted to the
                analysis queue.
        """

        # Store our capture speed.
        self.capture_speed = capture_speed

        # Create a packet delineator object.
        self.delineator     = USBHackDelineator(self)


    def get_microseconds(self):

        # Get the current time...
        current_time = datetime.now()



    def set_up_greatfet(self):
        """ Connects to our GreatFET, but does not yet start sampling. """

        import greatfet

        self.device = greatfet.GreatFET()

        # Load the Rhododendron firmware loadable into memory.
        try:
            data = read_rhododendron_m0_loadable()
        except (OSError, TypeError):
            raise


        # Bring our Rhododendron board online; and capture communication parameters.
        self.buffer_size, self.endpoint = self.device.apis.usb_analyzer.initialize(self.capture_speed, timeout=10000, comms_timeout=10000)

        # Start the m0 loadable for Rhododendron.
        self.device.m0.run_loadable(data)


    def run_rhododendron_capture(self):

        import usb

        # Start our sampling.
        transfer_buffer = array.array('B', b"\0" * self.buffer_size)

        while not self.termination_event.is_set():
            try:
                # Capture data from the device, and unpack it.
                try:
                    new_samples = self.device.comms.device.read(self.endpoint, transfer_buffer, SAMPLE_DELIVERY_TIMEOUT_MS)
                    samples = transfer_buffer[0:new_samples - 1]

                    self.delineator.submit_data(samples)

                except usb.core.USBError as e:
                    if e.errno != errno.ETIMEDOUT:
                        raise

            except KeyboardInterrupt:
                pass
            except usb.core.USBError as e:
                if e.errno == 32:
                    raise IOError("overflow -- could not pull data from the device fast enough!")
                else:
                    raise IOError("communications failure!")



    def run(self):
        """ Run a Rhododendron capture. """

        # Connect to our GreatFET...
        self.set_up_greatfet()

        # ... and start sampling.
        self.device.apis.usb_analyzer.start_capture()

        try:
            self.run_rhododendron_capture()

        finally:
            self.device.apis.usb_analyzer.stop_capture()




