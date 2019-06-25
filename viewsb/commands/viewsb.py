#!/usr/bin/env python3
"""
Main command-line runner for ViewSB.
"""

import sys
import argparse

from .. import ViewSBAnalyzer

from ..packet import USBPacketID

from ..frontends.cli import CLIFrontend
from ..frontends.tui import TUIFrontend

from ..backends.usbmon     import USBMonFileBackend
from ..backends.openvizsla import OpenVizslaBackend

from openvizsla import OVCaptureUSBSpeed



# For current test sanity, suppress SOF packets.
def suppress_packet(packet):
    return packet.pid == USBPacketID.SOF



def main():
    """ Main file runner for ViewSB. """

    # Add the common arguments for the runner application.
    parser = argparse.ArgumentParser(description="open-source USB protocol analyzer")
    parser.add_argument('--list-backends', action='store_true',
            help="list the available capture backends, then quit")
    parser.add_argument('--list-frontends', action='store_true',
            help="list the available UI frontends, then quit")


    if len(sys.argv) > 1:
        usbmon = sys.argv[1]
    else:
        usbmon = '/dev/usbmon0'

    backend  = (USBMonFileBackend, (usbmon, ) )
    #backend  = (OpenVizslaBackend, (OVCaptureUSBSpeed.HIGH, suppress_packet, ))

    frontend = (TUIFrontend, ())
    #frontend = (CLIFrontend, ())

    # Create our analyzer object.
    analyzer = ViewSBAnalyzer(backend, frontend)

    # Run the analyzer.
    analyzer.run()


if __name__ == "__main__":
    main()
