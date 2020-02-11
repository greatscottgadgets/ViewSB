#
# This file is part of ViewSB.
#
""" Work in progress backend for LUNA. """

# pylint: disable=maybe-no-member,access-member-before-definition

import sys
import errno
import argparse
from datetime import datetime

from ..backend import ViewSBBackend
from ..packet import USBPacket

try:
    from luna.gateware.applets.analyzer import \
        USBAnalyzerConnection, \
        USB_SPEED_FULL, USB_SPEED_HIGH, USB_SPEED_LOW

except (ImportError, ModuleNotFoundError) as e:
    pass


class LUNABackend(ViewSBBackend):
    """ Capture backend that captures packets from a LUNA board. """

    UI_NAME = "luna"
    UI_DESCRIPTION = "LUNA hardware analyzers"


    @staticmethod
    def reason_to_be_disabled():

        # If we can't import LUNA, it's probably not installed.
        if not 'USBAnalyzerConnection' in globals():
            return "python luna package not available"

        return None


    @staticmethod
    def speed_from_string(string):
        speeds = {
            'high': USB_SPEED_HIGH,
            'full': USB_SPEED_FULL,
            'low':  USB_SPEED_LOW
        }

        try:
            return speeds[string]
        except KeyError:
            return None


    @classmethod
    def parse_arguments(cls, args, parent_parser=[]):

        # Parse user input and try to extract our class options.
        parser = argparse.ArgumentParser(parents=parent_parser, add_help=False)
        parser.add_argument('--speed', type=cls.speed_from_string, default='high',
                help="the speed of the USB data to capture [valid: {high, full, low}]")
        args, leftover_args = parser.parse_known_args()

        if args.speed is None:
            sys.stderr.write("speed must be 'high', 'full', or 'low'\n")
            sys.exit(errno.EINVAL)

        #  Return the class and leftover arguments.
        return (args.speed, ), leftover_args


    def __init__(self, capture_speed, suppress_packet_callback=None):
        """ Creates a new LUNA capture backend.

        Args:
            capture_speed -- The speed at which to capture.
        """

        # TODO: validate
        self.capture_speed = capture_speed

        # Set up our connection to the analyzer.
        self.analyzer = USBAnalyzerConnection()

        # Build our analyzer gateware, and configure our FPGA.
        self.analyzer.build_and_configure(capture_speed)


    def run_capture(self):

        # Capture a single packet from LUNA.
        raw_packet, timestamp, _ = self.analyzer.read_raw_packet()

        # TODO: handle flags
        packet = USBPacket.from_raw_packet(raw_packet, timestamp=timestamp)
        self.emit_packet(packet)

