#!/usr/bin/env python3
"""
Main command-line runner for ViewSB.


This file is part of ViewSB
"""

import sys
import argparse

from .. import ViewSBAnalyzer

# Import all of our backends, frontends, and decoders.
from ..backend import ViewSBBackend
from ..frontend import ViewSBFrontend

# Yes pylint, we know wildcard imports are bad practice, but it's actually necessary in this case because
# __subclasses__() only returns subclasses that have been imported.
# pylint: disable=W0401, W0614
from ..backends import *
from ..frontends import *
# pylint: enable=W0401, W0614

from ..decoders.filters import USBStartOfFrameFilter


def list_enumerables(enumerable_type, name, include_unavailable=True):
    """ Prints a list of all available (and optionally unavailable) backends. """

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


class ViewSBArgumentParser(argparse.ArgumentParser):
    """ Subclass of argparse.ArgumentParser that also stores a list of the argument names as self.arg_names.

    This is desirable because later I want to separate and group the subparser arguments.
    """

    def __init__(self, *args, **kwargs):

        self.arg_names = []

        super().__init__(*args, **kwargs)


    def add_argument(self, *args, **kwargs):
        """ Overrides ArgumentParser.add_argument()

        This performs all the normal functionality, but also stores the argument's name (`dest`) for later.
        """

        ret = super().add_argument(*args, **kwargs)

        # 'help' won't be in a Namespace object if it's not passed, so we don't really care about it.
        if ret.dest != 'help':
            self.arg_names.append(ret.dest)

        return ret


    def subparser_by_name(self, name):
        """ Convenience function that gets a subparser by name.

        Args:
            name -- The name of the subparser to return. This is the name passed to add_parser(), NOT
                the name passed to add.subparsers().
        """

        # Get the subparser action.
        # As far as I can tell, there can only ever be one of these,
        # because calling add_subparsers() more than once on the same parser errors.
        try:
            subparser_action = \
                next(action for action in self._subparsers._group_actions if action.nargs == argparse.PARSER)
        except StopIteration as e:
            raise KeyError('This parser does not have any subparsers.')

        return subparser_action.choices[name]


def main():
    """ Main file runner for ViewSB. """

    # Add the common arguments for the runner application.
    parser = ViewSBArgumentParser(description="open-source USB protocol analyzer")
    parser.arg_names = []

    parser.arg_names.append(parser.add_argument('--include-sofs', '-S', action='store_true',
        help="Include USB start-of-frame-markers in the capture; adds a lot of load & noise.").dest)
    parser.arg_names.append(parser.add_argument('--list-frontends', action='store_true',
        help='List the available capture backends, then quit.').dest)
    parser.arg_names.append(parser.add_argument('--list-backends', action='store_true',
        help='List the available UI frontends, then quit.').dest)


    #
    # Add backends.
    #

    backend_parsers = parser.add_subparsers(dest='backend', metavar='backend', required=False,
        help='The capture backend to use.')
    for backend in ViewSBBackend.available_subclasses():

        # Create a subparser for each backend...
        parser_for_backend = backend_parsers.add_parser(backend.UI_NAME)

        # ...and add its respective options (if any).
        backend.add_options(parser_for_backend)


        #
        # Add frontends.
        #

        # HACK: This is truly terrible, but it seems
        # this is argparse's only way to make nested 'subcommands'.

        frontend_parsers = parser_for_backend.add_subparsers(dest='frontend',
            metavar='frontend', required=False, help='The UI frontend to use.')

        for frontend in ViewSBFrontend.available_subclasses():

            # Create a sub-subparser for each available frontend...
            parser_for_frontend = frontend_parsers.add_parser(frontend.UI_NAME)

            # ...and add its respective options (if any).
            frontend.add_options(parser_for_frontend)


    # HACK: This is a 'fake' argument that makes the help text look right if you pass --help without a backend,
    # since 'frontend' is an argument that is handled by each backend subparser.
    parser.add_argument('_frontend', help='The UI frontend to use.', nargs='?', metavar='frontend')


    args = parser.parse_args()


    if args.list_backends:
        list_enumerables(ViewSBBackend, 'backends')

        if not args.list_frontends:
            sys.exit(0)

    if args.list_frontends:
        list_enumerables(ViewSBFrontend, 'frontends')
        sys.exit(0)

    if not args.backend:

        # Emulate the argparse error message and exit code.
        # Note that we don't set required=True for backend because we want the user to be able to
        # --list-backends without specifying a backend.
        parser.error('{}: error: the following arguments are required: backend'.format(parser.prog))

    if not args.frontend:
        args.frontend = 'tui'

    # print(args)
    args_dict = vars(args)

    # Separate the groups arguments so we can pass them where they belong.

    backend_subparser = parser.subparser_by_name(args.backend)
    backend_args = {key: args_dict[key] for key in args_dict.keys() & backend_subparser.arg_names}

    frontend_subparser = backend_subparser.subparser_by_name(args.frontend)
    frontend_args = {key: args_dict[key] for key in args_dict.keys() & frontend_subparser.arg_names}

    backend_class = ViewSBBackend.get_subclass_from_name(args.backend)
    backend = (backend_class, backend_args)


    frontend_class  = ViewSBFrontend.get_subclass_from_name(args.frontend)
    frontend = (frontend_class, frontend_args)

    # Create our analyzer object.
    analyzer = ViewSBAnalyzer(backend, frontend)

    # Unless we're including SOFs, filter them out.
    if not args.include_sofs:
        analyzer.add_decoder(USBStartOfFrameFilter, to_front=True)

    # Run the analyzer.
    analyzer.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
