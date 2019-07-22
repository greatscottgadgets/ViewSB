"""
Basic dump-packets-to-the-console UI for ViewSB.


This file is part of ViewSB
"""

from ..frontend import ViewSBFrontend


class CLIFrontend(ViewSBFrontend):
    """ Simplest possible frontend: print our packets. """

    UI_NAME = 'cli'
    UI_DESCRIPTION = 'extremely simple UI that simply prints each packet'


    def handle_incoming_packet(self, packet):
        """ Render any incoming packets to our UI. """
        # just print; no fancy frontend
        print(repr(packet))




