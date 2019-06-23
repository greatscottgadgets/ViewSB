"""
Basic dump-packets-to-the-console UI for ViewSB.
"""

from ..frontend import ViewSBFrontend


class CLIFrontend(ViewSBFrontend):
    """ Simplest possible frontend: print our packets. """


    def __init__(self):
        """ Creates a new CLI display frontend. """
        pass


    def handle_incoming_packet(self, packet):
        """ Render any incoming packets to our UI. """
        # just print; no fancy frontend
        print(repr(packet))




