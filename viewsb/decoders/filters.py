
"""
Core decoders that handle manipulation of standard USB packets.

Includes functionality for e.g. breaking packets into transfers / transactions.


This file is part of ViewSB
"""

from usb_protocol.types import USBPacketID

from ..decoder import ViewSBDecoder
from ..packet import USBPacket


class USBPacketFilter:
    """ Mix-in for filters that want to filter a given packet. """

    INCLUDE_IN_ALL = False

    def should_filter_packet(self, packet):
        """ Function to override -- this is where you determine which packets should be filtered. """
        return False


    def can_handle_packet(self, packet):
        """ Simple definition of can_handle_packet that defers to should_filter_packet. """
        return self.should_filter_packet(packet)


    def consume_packet(self, packet):
        """ Trivial implementation of consume_packet that silently discards all packets consumed. """
        pass


class USBStartOfFrameFilter(USBPacketFilter, ViewSBDecoder):
    """ Filter that eliminates SOFs. """

    def should_filter_packet(self, packet):
        return (type(packet) is USBPacket) and (packet.pid is USBPacketID.SOF)
