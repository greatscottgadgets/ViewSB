"""
iCE40-usbtrace backend for ViewSB


This file is part of ViewSB
"""

# pylint: disable=maybe-no-member,access-member-before-definition

from datetime import timedelta

from ..backend import ViewSBBackend
from ..packet import USBPacket

try:
    from ice40usbtrace import ICE40USBTrace, USBPacketHandler, packet

    class ViewSBPacketHandler(USBPacketHandler):
        """ iCE40-usbtrace USB event sink that submits packets for decoding. """

        def __init__(self, backend, suppress_packet_callback=None):
            # Store a reference to our parent backend, so we can submit USB data via it.
            self.backend = backend

            # Mark ourselves as having no packet pending.
            self.pending_packet = None

            # Store the callback we use to determine if we should suppress packets.
            self.suppress_packet_callback = suppress_packet_callback

        def _emit_packet(self, packet):
            """ Emits a packet to the main decoder thread for analysis. """
            self.backend.emit_packet(packet)

        def _should_be_suppressed(self, packet):
            """ Returns true iff the given packet should be suppressed, e.g. because of a user-provided condition. """
            if callable(self.suppress_packet_callback):
                return self.suppress_packet_callback(packet)
            else:
                return False

        def handle_packet(self, in_packet : packet.USBPacket):
            """ Called whenever the iCE40-usbtrace device detects a new USB packet. """

            # Packet we get from usb trace is pre-parsed, we need raw bytes
            raw_packet = in_packet.raw_bytes()

            # Compute timestamp
            timestamp_us = in_packet.hdr.expanded_ts / 24

            # Convert to a ViewSB packet
            packet = USBPacket.from_raw_packet(
                raw_packet,
                timestamp=timedelta(microseconds=timestamp_us),
            )

            # Assume the packet isn't one we're suppressing, emit it to our stack.
            if not self._should_be_suppressed(packet):
                self._emit_packet(packet)

except (ImportError, ModuleNotFoundError):
    pass


class ICE40USBTraceBackend(ViewSBBackend):
    """ Capture backend that captures packets from iCE40-usbtrace. """

    UI_NAME = "ice40usbtrace"
    UI_DESCRIPTION = "iCE40-usbtrace hardware analyzers"


    @staticmethod
    def reason_to_be_disabled():
        # The main reason we'd not be available would be that pyopenvizsla
        # isn't importable (and thus likely not installed).
        if not 'ViewSBPacketHandler' in globals():
            return "ice40usbtrace package (driver) not available"

        return None

    @classmethod
    def add_options(cls, parser):
        pass

    def __init__(self, suppress_packet_callback=None):
        """ Creates a new iCE40-usbtrace capture backend.

        Args:
            suppress_packet_callback -- A callback function that determines
                which packets should be dropped before being submitted to the
                analysis queue.
        """

        super().__init__()

        # Create a new iCE40-usbtrace device
        self.device = ICE40USBTrace(packet_handler=ViewSBPacketHandler(self, suppress_packet_callback))

    def setup(self):
        # Start capture
        self.device.start()

    def handle_termination(self):
        # Stop capture
        self.device.stop()

    def run_capture(self):
        # Run one iteration manually
        self.device.usb_context.handleEvents()
