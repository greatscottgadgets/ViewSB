"""
USBProxy backend for ViewSB


This file is part of ViewSB
"""

# pylint: disable=maybe-no-member,access-member-before-definition

from datetime import datetime, timedelta

from usb_protocol.types import USBPacketID, USBDirection

from ..backend import ViewSBBackend
from ..packet import USBControlTransfer, USBSetupTransaction, USBTransaction

try:
    from facedancer import FacedancerUSBApp
    from facedancer.USBProxy import USBProxyDevice, USBProxyFilter
    from facedancer.filters.standard import USBProxySetupFilters

    class ViewSBProxyObserver(USBProxyFilter):
        """
        USBProxy filter that observes all packets passing through it, without modification.
        Submits the relevant data to ViewSB for processing.
        """

        def __init__(self, backend):

            # Store a reference to our parent backend, so we can submit USB data via it.
            self.backend = backend

            # Mark ourselves as having no packet pending.
            self.pending_packet = None


        def _emit_packet(self, packet):
            """ Emits a packet to the main decoder thread for analysis. """
            self.backend.emit_packet(packet)

        def _emit_pending_packet(self, stalled=False):
            """ Emits any pending packet before moving on to the next one. """

            # If we have a pending packet,
            if self.pending_packet:
                self.pending_packet.stalled = stalled
                self._emit_packet(self.pending_packet)
                self.pending_packet = None

        def generate_data_transfer_packet(self, direction, ep_num, data, stalled, pid=None, timestamp=None):
            """ Generates a packet for a given USBProxy data transfer. """

            # FIXME: automate packet toggling if this is None
            if pid is None:
                pid = USBPacketID.DATA0

            if timestamp is None:
                timestamp = self.backend.get_microseconds()

            fields = {

                # Generic fields.
                'timestamp':       timestamp,
                'device_address':  self._get_device_address(),
                'endpoint_number': ep_num,

                # Transfer fields.
                'token':           direction.token(),
                'data_pid':        pid if data else None,
                'handshake':       USBPacketID.STALL if stalled else USBPacketID.ACK,

                # Data fields.
                'data':            data
            }

            # FIXME: wrap this in a transaction object!
            return USBTransaction(**fields)

        def _get_device_address(self):
            return self.backend.proxy.libusb_device.address


        def generate_handshake_transaction_packet(self, direction, stalled=False, ep_num=0, timestamp=None):
            """ Generates a handshake transfer packet to terminate a control transfer. """

            if timestamp is None:
                timestamp = self.backend.get_microseconds()
            return USBTransaction(token=direction.token(), data_pid=USBPacketID.DATA1,
                handshake=USBPacketID.STALL if stalled else USBPacketID.ACK, timestamp=timestamp, data=bytes([]))


        def generate_control_transfer_packet(self, req, data, stalled=False, ep_num=0):
            """ Generates a packet for a given USBProxy control transfer. """

            timestamp = self.backend.get_microseconds()

            # Read the address of the device we're talking to.
            address = self.backend.proxy.libusb_device.address

            # Build three synthetic transactions that compose our control request...
            setup = USBSetupTransaction.from_setup_data(
                req.raw(),
                device_address=address,
                timestamp=timedelta(microseconds=timestamp),
            )
            last_direction = USBDirection.OUT

            # If we have a data stage, generate a packet for it.
            if data:

                # If this is an IN request, a STALL is indicated during the DATA stage.
                # Otherwise, stalls are always handled during the handshake; so we'll never stall
                # the data stage.
                data_stall = stalled if setup.request_direction.is_in() else False

                # Update the last tranferred direction to match the direction of the data stage.
                last_direction = setup.request_direction

                # Generate the data transfer itself.
                data_transfer = self.generate_data_transfer_packet(setup.request_direction, ep_num,
                    data, data_stall, pid=USBPacketID.DATA1, timestamp=timestamp)
            else:
                data_transfer = None


            # Generate the handshake packet.

            # If we've already stalled during the data phase, there's no handshake phase.
            if setup.request_direction.is_in() and data and stalled:
                handshake = None

            #Otherwise, generate the handshake packet.
            else:
                # The handshake packet is always in the direction opposite the last transfer.
                direction = last_direction.reverse()
                handshake = self.generate_handshake_transaction_packet(direction, stalled, ep_num, timestamp=timestamp)

            # Build a Control Transfer from the three parts, and return it.
            return USBControlTransfer.from_subordinates(setup, data_transfer, handshake)

        def filter_control_in(self, req, data, stalled):
            # This starts a new transaction, so emit any pending packets.
            self._emit_pending_packet()

            data = bytes(data)

            # Emit the packet for the given control request.
            self._emit_packet(self.generate_control_transfer_packet(req, data, stalled))

            # ... and don't modify the packet itself.
            return req, data, stalled

        def filter_control_out(self, req, data):
            # This starts a new transaction, so emit any pending packets.
            self._emit_pending_packet()

            data = bytes(data)

            # We have most of a control request, but we don't yet have whether the given request stalled.
            # We'll generate the request, but leave it pending until we get another request (and thus know that the
            # packet did not stall.)
            self.pending_packet = self.generate_control_transfer_packet(req, data)

            # Don't modify the packet itself.
            return req, data

        def handle_out_request_stall(self, req, data, stalled):

            # We just received a stall on our pending packet. Emit it as stalled.
            self._emit_pending_packet(stalled=True)

            # Don't modify the request otherwise.
            return req, data, stalled


        def filter_in(self, ep_num, data):
            # This starts a new transaction, so emit any pending packets.
            self._emit_pending_packet()

            data = bytes(data)

            # Emit the packet for the given control request.
            # FIXME: this should capture stalls!
            self._emit_packet(self.generate_data_transfer_packet(USBDirection.IN, ep_num, data, False))

            # ... and don't modify the data itself.
            return ep_num, data


        def filter_out(self, ep_num, data):
            # This starts a new transaction, so emit any pending packets.
            self._emit_pending_packet()

            data = bytes(data)

            # We have most of a transfer, but we don't yet have whether the given transfer stalled.
            # We'll generate the packet, but leave it pending until we get another request (and thus know that it did not stall.)
            self.pending_packet = self.generate_data_transfer_packet(USBDirection.IN, ep_num, data, False)

            # ... and don't modify the data itself.
            return ep_num, data


        def handle_out_stall(self, ep_num, data, stalled):

            # We just received a stall on our pending packet. Emit it as stalled.
            self._emit_pending_packet(stalled=True)

            # And don't modify anything.
            return ep_num, data, stalled


        def handle_termination(self):
            """ Handles termination of the capture. """

            # Emit our pending packet, if we have one.
            self._emit_pending_packet(False)

except (ImportError, ModuleNotFoundError):
    pass



class USBProxyBackend(ViewSBBackend):
    """ Capture backend that captures packets as they're proxied from device to device. """

    UI_NAME = "usbproxy"
    UI_DESCRIPTION = "display packets proxied by FaceDancer's usbproxy"

    @staticmethod
    def reason_to_be_disabled():

        # The main reason we'd not be available would be that pyopenvizsla
        # isn't importable (and thus likely not installed).
        if not 'ViewSBProxyObserver' in globals():
            return "facedancer module not available"

        return None


    def __init__(self, vendor_id, product_id, additional_filters=None):
        """
        Creates a new USBProxy instance that captures all passed packets to ViewSB.

        Args:
            vendor_id -- The vendor ID of the device to be proxied.
            product_id -- The product ID of the device to be proxied.
            additional_filters -- A list of any additional filters to be installed in the proxy stack.
        """

        super().__init__()
        # Create the backend USBProxy instance that will perform our captures...
        facedancer_app = FacedancerUSBApp()
        self.proxy = USBProxyDevice(facedancer_app, idVendor=vendor_id, idProduct=product_id)

        # ... add the necessary filters to perform our magic...
        self.proxy.add_filter(ViewSBProxyObserver(self))
        self.proxy.add_filter(USBProxySetupFilters(self.proxy))

        # ... and add any other filters passed in.
        if additional_filters:
            for additional_filter in additional_filters:
                self.proxy.add_filter(additional_filter)

        # Set up our connection to the device-to-be-proxied.
        self.proxy.connect()


    @classmethod
    def add_options(cls, parser):

        def hex_int(i):
            return int(i, 16)

        parser.add_argument('-v', '--vid', type=hex_int, required=True, dest='vendor_id',
            help="USB Vendor ID in hex")
        parser.add_argument('-p', '--pid', type=hex_int, required=True, dest='product_id',
            help="USB Product ID in hex")


    def get_microseconds(self):

        # Get the current time...
        current_time = datetime.now()

        # ... and figure out the microseconds since the start.
        return (current_time - self.start_time).microseconds


    def run(self):

        # Record the time at which the capture is starting.
        self.start_time = datetime.now()

        # And call the base run, function.
        super().run()


    def run_capture(self):
        """ Perform a single iteration of our capture -- essentially services the FaceDancer IRQs. """

        # If the start time wasn't set (e.g. the user is strumming our strings manually), set it.
        if self.start_time is None:
            self.start_time = datetime.now()

        # FIXME: call a run_once on the FaceDancer scheduler; don't touch its internals
        for task in self.proxy.scheduler.tasks:
            task()


    def handle_termination(self):
        """ Handles termination of the capture. """

        # Pass the termination on to our backend.
        self.backend.handle_termination()
