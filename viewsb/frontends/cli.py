"""
Basic dump-packets-to-the-console UI for ViewSB.
"""

from ..frontend import ViewSBFrontend


class CLIFrontend(ViewSBFrontend):
    """ Capture backend that captures packets from OpenVizsla. """


    def __init__(self):
        """ Creates a new CLI display frontend. """
        pass


    def handle_incoming_packet(self, packet):

        # XXX: temporary, for debug only
        # just print; no fancy frontend
        print(repr(packet))




