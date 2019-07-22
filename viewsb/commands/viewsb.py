#!/usr/bin/env python3
"""
Main command-line runner for ViewSB.


This file is part of ViewSB
"""

import sys
import errno
import argparse

from .. import ViewSBAnalyzer

from ..packet import USBPacketID

from ..frontends.cli import CLIFrontend
from ..frontends.tui import TUIFrontend

# Import all of our backends, frontends, and decoders.
from ..backend import ViewSBBackend
from ..backends import *

from ..frontend import ViewSBFrontend
from ..frontends import *

from ..decoders.filters import USBStartOfFrameFilter


# For current test sanity, suppress SOF packets.
def suppress_packet(packet):
    return packet.pid == USBPacketID.SOF


def list_enumerables(enumerable_type, name, include_unavailable=True, quit_after=True):
    """ Prints a list of all availale (and optionally unavailable) backends. """

    # Print the available backends...
    print("Available {}:".format(name))
    for backend in enumerable_type.available_subclasses():
        print("\t{:12} -- {}".format(backend.UI_NAME, backend.UI_DESCRIPTION))
    print()

    # ... and if, desired, print any unavailable ones.
    unavailable = list(enumerable_type.unavailable_subclasses())

    if include_unavailable and unavailable:

        print("Unavailable {}:".format(name))
        for backend, reason in unavailable:
            print("\t{:12} -- {}".format(backend.UI_NAME, reason))
        print()

    if quit_after:
        sys.exit(0)


def error(message):
    """ Convenience method to print a message to the stderr. """
    sys.stderr.write("{}\n".format(message))
    sys.stderr.flush()


def fatal(message, return_code=errno.EINVAL):
    """ Convenience method to print a message to the stderr. """
    error(message)
    sys.exit(return_code)


def main():
    """ Main file runner for ViewSB. """

    # Add the common arguments for the runner application.
    parser = argparse.ArgumentParser(description="open-source USB protocol analyzer")

    # General commands.
    parser.add_argument('backend', type=ViewSBBackend.get_subclass_from_name, nargs='?',
            help='the backend to use as a packet source')
    parser.add_argument('frontend', type=ViewSBFrontend.get_subclass_from_name, nargs='?',
            help='the frontend to use to display/save packets [default: tui]')

    # Flags.
    parser.add_argument('--list-backends', action='store_true',
            help="list the available capture backends, then quit")
    parser.add_argument('--list-frontends', action='store_true',
            help="list the available UI frontends, then quit")
    parser.add_argument('--include-sofs', '-S', action='store_true',
            help="include USB start-of-frame markers in the capture; adds a load of load & noise")

    # Parse our known arguments.
    args, leftover_args = parser.parse_known_args()

    if args.list_backends:
        list_enumerables(ViewSBBackend, 'backends', quit_after=not args.list_frontends)
    if args.list_frontends:
        list_enumerables(ViewSBFrontend, 'frontends')

    # Check for the validity of our arguments.
    if args.backend is None:
        fatal("invalid backend; use --list-backends for a list of valid backends")
    if not args.frontend:
        args.frontend = TUIFrontend

    backend_args, leftover_args  = args.backend.parse_arguments(leftover_args, [parser])
    frontend_args, leftover_args = args.frontend.parse_arguments(leftover_args, [parser])

    # Instantiate the backend and frontend objects.
    backend  = (args.backend, backend_args)
    frontend = (args.frontend, frontend_args)

    if leftover_args:
        fatal("unexpected arguments: {}".format(' '.join(leftover_args)))

    # Create our analyzer object.
    analyzer = ViewSBAnalyzer(backend, frontend)

    # Unless we're including SOFs, instantiate a SOF filter to filter them out.
    if not args.include_sofs:
        analyzer.add_decoder(USBStartOfFrameFilter, to_front=True)

    # Run the analyzer.
    analyzer.run()


if __name__ == "__main__":
    main()
