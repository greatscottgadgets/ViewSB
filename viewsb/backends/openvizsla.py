"""
OpenVizsla backend for ViewSB
"""

# pylint: disable=maybe-no-member,access-member-before-definition

from datetime import datetime

from ..backend import ViewSBBackend
from ..packet import USBPacket

from openvizsla import OVDevice, OVCaptureUSBSpeed, USBEventSink


class ViewSBEventSink(USBEventSink):
    """ OpenVizsla USB event sink that submits packets for decoding. """


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


    def handle_usb_packet(self, timestamp, raw_packet, flags):
        """ Called whenever the OpenVizsla device detects a new USB packet. """

        # For now, ignore any populated USB packets as noise.
        if not len(raw_packet):
            return

        # TODO: convert flags to status?
        packet = USBPacket.from_raw_packet(raw_packet, timestamp=timestamp)

        # Assume the packet isn't one we're suppressing, emit it to our stack.
        if not self._should_be_suppressed(packet):
            self._emit_packet(packet)




class OpenVizslaBackend(ViewSBBackend):
    """ Capture backend that captures packets from OpenVizsla. """


    def __init__(self, capture_speed, suppress_packet_callback=None):
        """ Creates a new OpenVizsla capture backend.

        Args:
            capture_speed -- The speed at which to capture.
        """

        # TODO: validate
        self.capture_speed    = capture_speed

        # Create a new OpenVizsla device; but don't yet try to connect to it.
        self.ov_device = OVDevice()

        # And create the packet sink we'll use to get data from the OV device.
        self.packet_sink = ViewSBEventSink(self, suppress_packet_callback)
        self.ov_device.register_sink(self.packet_sink)



    def run(self):
        """ Run an OpenVizsla capture. """

        self.ov_device.open(reconfigure_fpga=True)

        try:
            halt_callback = lambda _ : self.termination_event.is_set()
            self.ov_device.run_capture(self.capture_speed, halt_callback=halt_callback)

        finally:
            self.ov_device.ensure_capture_stopped()
            self.ov_device.close()



