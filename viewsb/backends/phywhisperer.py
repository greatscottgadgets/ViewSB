"""
PhyWhisperer-USB backend for ViewSB
Inspired by OpenVizsla backend


This file is part of ViewSB
"""

# pylint: disable=maybe-no-member,access-member-before-definition

import sys
import errno
import argparse
import time
from datetime import datetime

from ..backend import ViewSBBackend
from ..packet import USBPacket, USBControlTransfer, USBPacketID


try:
    from phywhisperer import USBEventSink, usb as pw

    class ViewSBEventSink(USBEventSink):
        """ PhyWhisperer USB event sink that submits packets for decoding. """


        def __init__(self, backend, suppress_packet_callback=None):

            # Store a reference to our parent backend, so we can submit USB data via it.
            self.backend = backend

            # Store the callback we use to determine if we should suppress packets.
            self.suppress_packet_callback = suppress_packet_callback


        def _emit_packet(self, packet):
            """ Emits a packet to the main decoder thread for analysis. """
            self.backend.emit_packet(packet)


        def handle_usb_packet(self, timestamp, raw_packet, flags):
            """ Called whenever the PhyWhisperer device detects a new USB packet. """

            # For now, ignore any unpopulated USB packets as noise.
            if not len(raw_packet):
                return

            packet = USBPacket.from_raw_packet(raw_packet, timestamp=timestamp)
            self._emit_packet(packet)


except (ImportError, ModuleNotFoundError) as e:
    pass



class PhyWhispererBackend(ViewSBBackend):
    """ Capture backend that captures packets from PhyWhisperer. """

    UI_NAME = "phywhisperer"
    UI_DESCRIPTION = "PhyWhisperer hardware sniffer"

    MAX_CAPTURE_SIZE = 8188
    MAX_PATTERN_SIZE = 64


    @staticmethod
    def reason_to_be_disabled():
        # The main reason we'd not be available would be that phywhisperer
        # isn't importable (and thus likely not installed).
        if not 'ViewSBEventSink' in globals():
            return "PhyWhisperer driver not available"

        return None


    @classmethod
    def parse_arguments(cls, args, parent_parser=[]):

        # Parse user input and try to extract our class options.
        parser = argparse.ArgumentParser(parents=parent_parser, add_help=False)
        parser.add_argument('--size', type=int, default=cls.MAX_CAPTURE_SIZE,
                help="capture size (0 = unlimited")
        parser.add_argument('--pattern', type=int, nargs='+', default=[0], choices=range(0,256),
                help="capture pattern (list of ints)")
        parser.add_argument('--mask', type=int, nargs='+', default=[0], choices=range(0,256),
                help="mask pattern (list of ints)")
        parser.add_argument('--addpattern', action='store_true',
                help="add pattern to captured data")
        parser.add_argument('--burst', action='store_true',
                help="read captured data in a single burst")
        args, leftover_args = parser.parse_known_args()


        if args.size not in range(0,cls.MAX_CAPTURE_SIZE+1):
            sys.stderr.write("size must be between 0 and %d (inclusive)\n" % cls.MAX_CAPTURE_SIZE)
            sys.exit(errno.EINVAL)

        if len(args.pattern) != len(args.mask):
            sys.stderr.write("pattern and mask must have same number of elements\n")
            sys.exit(errno.EINVAL)

        if len(args.pattern) > cls.MAX_PATTERN_SIZE:
            sys.stderr.write("pattern cannot have more than %s elements\n" % cls.MAX_PATTERN_SIZE)
            sys.exit(errno.EINVAL)

        #  Return the class and leftover arguments.
        return (args.size, args.burst, args.pattern, args.mask, args.addpattern), leftover_args


    def __init__(self, size, burst, pattern, mask, addpattern, suppress_packet_callback=None):
        """ Creates a new PhyWhisperer capture backend.

        Args:
            size: number of USB events to capture
            burst: read from capture FIFO in a single burst
            pattern: pattern match bytes
            mask: mask for pattern match bytes
            addpattern: the pattern match aren't captured; use this option to artificially
                insert them into the capture data
            suppress_packet_callback -- A callback function that determines
                which packets should be dropped before being submitted to the
                analysis queue.
        """

        from phywhisperer import usb as pw

        # Create a new PhyWhisperer device; but don't yet try to connect to it.
        self.pw_device = pw.Usb(viewsb=True)

        # And create the packet sink we'll use to get data from the PW device.
        self.packet_sink = ViewSBEventSink(self, suppress_packet_callback)
        self.pw_device.register_sink(self.packet_sink)
        self.pw_device.addpattern = addpattern
        self.size = size
        self.burst = burst
        self.pattern = pattern
        self.mask = mask


    def run(self):
        """ Run a PhyWhisperer capture. """

        # TODO: provide here an offline mode where we don't connect the device and instead
        # call a variant of run_capture which reads from a file instead
        self.pw_device.con(program_fpga=True)

        try:
            halt_callback = lambda _ : self.termination_event.is_set()
            self.pw_device.run_capture(size=self.size, burst=self.burst, pattern=self.pattern, mask=self.mask, halt_callback=halt_callback)

        finally:
            self.pw_device.close()


