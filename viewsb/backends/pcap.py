#
# This file is part of ViewSB.
#
""" Work in progress backend for PCAP files. """

# pylint: disable=maybe-no-member,access-member-before-definition


from datetime import timedelta
from time import sleep

from ..backend import ViewSBBackend
from ..packet import USBPacket

try:
    # https://pypi.org/project/pypcapfile/
    # https://github.com/kisom/pypcapfile
    from pcapfile import savefile

except (ImportError, ModuleNotFoundError):
    pass


class PcapBackend(ViewSBBackend):
    """ Capture backend that reads packets from a pcap file. """

    UI_NAME = "pcap"
    UI_DESCRIPTION = "pcap file reader"


    @staticmethod
    def reason_to_be_disabled():

        # If we can't import the savefile from pcapfile library, it's probably not installed.
        if not 'savefile' in globals():
            return "python pcapfile package not available"

        return None


    @classmethod
    def add_options(cls, parser):

        # Parse user input and try to extract our class options.
        parser.add_argument('--filename', dest='filename', default='', required=True,
            help="The pcap file to read from")


    def __init__(self, filename, suppress_packet_callback=None):
        """ Creates a new pcap file reader backend.

        Args:
            filename -- pcap file to read from.
        """

        super().__init__()

        self.filenane = filename
        self.pcapdata = None
        self.packet_index = 0
        self.packet_count = 0
        self.t_start = 0
        self.t_start_us = 0

        # Store the callback we use to determine if we should suppress packets.
        self.suppress_packet_callback = suppress_packet_callback

    def _should_be_suppressed(self, packet):
        """ Returns true if the given packet should be suppressed, e.g. because of a user-provided condition. """

        if callable(self.suppress_packet_callback):
            return self.suppress_packet_callback(packet)

        return False


    def setup(self):
        self.setup_queue.put('Opening file ' + self.filenane +' ...')

        pcapfile = open(self.filenane, 'rb')
        self.pcapdata = savefile.load_savefile(pcapfile,verbose=False)
        pcapfile.close()


        self.packet_index = 0
        self.packet_count = len(self.pcapdata.packets)

        # report timestamps as offset since first packet,
        # (aligned with the way wireshark reports timestamps)
        self.t_start = self.pcapdata.packets[0].timestamp
        self.t_start_us = self.pcapdata.packets[0].timestamp_us


    def run_capture(self):

        # while not yet at the end of the file keep pulling packets....
        if self.packet_index < self.packet_count:

            # read a single packet from pcap file.
            pkt = self.pcapdata.packets[self.packet_index]
            raw_packet = bytearray(pkt.raw())


            timestamp_s = pkt.timestamp-self.t_start

            # openvizsla pcap files use nanosecond resolution format; ViewSB expects microseconds
            if self.pcapdata.header.ns_resolution:
                timestamp_us = (pkt.timestamp_us - self.t_start_us)/1000
            else:
                timestamp_us = (pkt.timestamp_us - self.t_start_us )

            self.packet_index = self.packet_index + 1

            # TODO: handle flags
            packet = USBPacket.from_raw_packet(
                raw_packet,
                timestamp=timedelta(microseconds=timestamp_us, seconds = timestamp_s),
            )
            # Assume the packet isn't one we're suppressing, emit it to our stack.
            if not self._should_be_suppressed(packet):
                self.emit_packet(packet)
        else:
            # FIXME - nothing to do anymore; stay idle
            #         should be some way to indicate the gui process to stop capturing
            if self.pcapdata:
                self.pcapdata = None
            sleep(5)
