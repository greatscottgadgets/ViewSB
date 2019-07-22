"""
Core decoder definitions for ViewSB.


This file is part of ViewSB
"""

from .frontend import ViewSBEnumerableFromUI

class UnhandledPacket(IOError):
    """
    Exception that can be emitted by decoders in `consume_packet` to "change their mind"
    about consuming a packet. This cancel the pending consumption.
    """
    pass


class ViewSBDecoder(ViewSBEnumerableFromUI):
    """ Base class for ViewSB decoders, which can consume and emit ViewSBPackets.

    Typically, decoders operate by consuming one or more ViewSBPacket objects, and
    then emitting one or more more-specific ViewSB subclasses.
    """

    # Indicates whether the given decoder should be included in all_decoders().
    # If more granular logic is needed, the class can override `include_in_all`.
    INCLUDE_IN_ALL = True


    def __init__(self, analyzer):
        """ Common initializer for ViewSB decoders.

        Subclasses can accept more arguments than these; but they
        should all have default values; or this won't be included in "all decoders".
        """

        self.analyzer = analyzer


    @classmethod
    def include_in_all(cls):
        """ Returns whether the given class should be included in get_all_decoders(). """

        # By default, return the value of the INCLUDE_IN_ALL class variable.
        return cls.INCLUDE_IN_ALL


    @classmethod
    def all_decoders(cls):
        """ Returns all decoders that can currently be instantiated. """

        # TODO: filter this to only include ones with the correct arguments.
        subclasses = cls.__subclasses__()
        return [subclass for subclass in subclasses if subclass.include_in_all()]


    def can_handle_packet(self, packet):
        """
        Accept all packets by default; this allows classes to instead raise
        UnhandledPacket to inline-reject packets.
        """

        return True


    def handle_packet(self, packet):
        """ Packet handler -- called as we work through the analysis queue.

        Returns True if the packet should be consumed by this decoder (and
        thus not passed to any other decoders); or False if this decoder isn't
        the correct consumer for this packet.

        If this function isn't overridden by a subclass, it should override
        `can_handle_packet` and `consume_packet` instead.
        """

        # Default implementation: use can_handle_packet to determine if we
        # handle the given type of packet; and call `.consume_packet` to
        # consume the given packet.

        if self.can_handle_packet(packet):
            try:
                self.consume_packet(packet)
                return True
            except UnhandledPacket:
                return False
        else:
            return False


    def consume_packet(self, packet):
        """
        Packet handler -- called for packets we're in the process of consuming.
        Used by the default implementation of handle_packet.
        """
        raise NotImplementedError("decoder must override either handle_packet or consume_packet!")


    def emit_packet(self, packet):
        """ Emits a given packet; placing it at the end of the decoder queue. """
        self.analyzer.add_packet_to_analysis_queue(packet)


    def handle_termination(self, packet):
        """ Called when the given decoder is terminated; allows any half-processed packets to be flushed """
        pass

