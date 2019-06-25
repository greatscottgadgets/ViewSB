"""
Core decoders that handle manipulation of standard USB packets.

Includes functionality for e.g. breaking packets into transfers / transactions.
"""

import bitstruct
import collections

from ..decoder import ViewSBDecoder, UnhandledPacket
from ..packet import USBPacket, MalformedPacket, USBTokenPacket, USBHandshakePacket, \
     USBDataPacket, USBTransaction, USBSetupTransaction, USBDataTransaction, \
     USBSetupTransfer, USBDataTransfer, USBStatusTransfer
from ..usb_types import USBPacketID


class USBPacketSpecializer(ViewSBDecoder):
    """
    Decoder that converts raw USB packets into specialized ones by PID group.
    e.g. can convert a raw USB packet into a TokenPacket, a DataPacket, or etc.
    """

    # Various USB packets size constant.
    TOKEN_PAYLOAD_LENGTH     = 2
    HANDSHAKE_PAYLOAD_LENGTH = 0

    CRC16_LENGTH             = 2
    MAXIMUM_PACKET_PAYLOAD   = 1026

    def can_handle_packet(self, packet):
        return type(packet) == USBPacket

    def _consume_token_packet(self, packet):
        """ Consumes a packet known to be a token packet. """

        fields = packet.__dict__

        # If our packet isn't the right length for a token, emit
        # a malformed packet.
        if len(packet.data) != self.TOKEN_PAYLOAD_LENGTH:
            self.emit_packet(MalformedPacket(**fields))
            return

        # Unpack the fields of the token.
        address, endpoint, crc5 = bitstruct.unpack('u7u4u5', packet.data)
        fields['device_address']  = address
        fields['endpoint_number'] = endpoint

        # Populate a USBTokenPacket with the relevant information...
        new_packet = USBTokenPacket(crc5=crc5, **fields)

        # ... and emit the new packet.
        self.emit_packet(new_packet)


    def _consume_handshake_packet(self, packet):
        """ Consumes a packet known to be a handshake packet. """

        new_packet = USBHandshakePacket(**packet.__dict__)
        self.emit_packet(new_packet)


    def _consume_data_packet(self, packet):
        """ Consumes a packet known to be a data packet. """

        fields = packet.__dict__

        # If our packet doesn't have at least the CRC length, it's malformed.
        # a malformed packet.
        if not (self.CRC16_LENGTH <= len(packet.data) < self.MAXIMUM_PACKET_PAYLOAD):
            self.emit_packet(MalformedPacket(**fields))
            return

        # Copy the original data, but extract the CRC16.
        crc16          = fields['data'][-2:]
        fields['data'] = packet.data[:-2]

        # Populate a USBDataPacket with the relevant information...
        new_packet = USBDataPacket(crc16=crc16, **fields)

        # ... and emit the new packet.
        self.emit_packet(new_packet)


    def consume_packet(self, packet):

        # Convert the packet according to its group.
        if packet.pid.is_token():
            self._consume_token_packet(packet)
        elif packet.pid.is_handshake():
            self._consume_handshake_packet(packet)
        elif packet.pid.is_data():
            self._consume_data_packet(packet)


        # If we didn't have a strategy for consuming the given packet
        # fail out and don't consume the packet.
        else:
            raise UnhandledPacket()


class USBTransactionDecoder(ViewSBDecoder):
    """ Class that groups sequences of packets into Transactions. """

    def __init__(self, analyzer):

        # Start a new list of packets absorbed.
        self.packets_captured = []
        super().__init__(analyzer)


    def can_handle_packet(self, packet):
        return type(packet) in (USBTokenPacket, USBDataPacket, USBHandshakePacket)


    def _last_captured(self):
        if not self.packets_captured:
            return None
        else:
            return self.packets_captured[-1]

    def _first_captured(self):
        if not self.packets_captured:
            return None
        else:
            return self.packets_captured[0]

    def emit_transaction(self, sequence_error=False):

        fields = self._first_captured().__dict__.copy()

        fields['token']     = self._first_captured().pid
        fields['handshake'] = self._last_captured().pid

        if len(self.packets_captured) == 3:
            fields['data_pid'] = self.packets_captured[1].pid
            fields['data'] = self.packets_captured[1].data[:]
        else:
            fields['data_pid'] = None
            fields['data'] = None

        # Move the captured packets into our new transaction; and create a
        # new buffer for future fields.
        fields['subordinate_packets'] = self.packets_captured
        self.packets_captured = []

        self.emit_packet(USBTransaction(**fields))


    def consume_packet(self, packet):

        # Case 1: if this is a token packet, and we've not started a transaction, capture it.
        if isinstance(packet, USBTokenPacket) and not self.packets_captured:
            self.packets_captured.append(packet)

        # Case 2: if this is a data packet, and it's following a token packet, capture it.
        elif isinstance(packet, USBDataPacket) and isinstance(self._last_captured(), USBTokenPacket):
            self.packets_captured.append(packet)

        elif isinstance(packet, USBHandshakePacket) and isinstance(self._first_captured(), USBTokenPacket):
            self.packets_captured.append(packet)
            self.emit_transaction(sequence_error=False)

        else:
            self.packets_captured.append(packet)
            self.emit_transaction(sequence_error=True)



class USBTransactionSpecializer(ViewSBDecoder):
    """
    Decoder that converts transactions into more-specific types of transactions.
    """

    def can_handle_packet(self, packet):
        return type(packet) is USBTransaction


    def consume_packet(self, packet):

        # If we have a SETUP token, convert this to a SetupTransaction.
        if packet.pid is USBPacketID.SETUP:
                specialized_type = USBSetupTransaction
        # If we have a DATA token, convert this to a DataTransaction.
        elif packet.pid.is_data():
                specialized_type = USBDataTransaction

        # If it's any other kind of transaction, emit it directly.
        # FIXME: support things like ping?
        else:
            raise UnhandledPacket()

        # Specialize the packet into the given type.
        transaction = specialized_type(**packet.__dict__)
        self.emit_packet(transaction)






class USBTransferGrouper(ViewSBDecoder):
    """
    Decoder that converts sequences of consecutive/coherent transactions into transfers.
    """

    # Don't include this specializer in all; it's not complete.
    INCLUDE_IN_ALL = False

    # List of packet types that conclude a transfer.
    OPENING_TRANSFER_TYPES = [USBSetupTransaction]


    def __init__(self, analyzer):
        super().__init__()

        # Create a mapping of packets captured.
        # These can be non-contiguous, so
        self.packets_captured = collections.defaultdict(lambda key : [])


    def can_handle_packet(self, packet):
        """ We can handle any non-special transaction. """
        return type(packet) in (USBSetupTranaction, USBDataTransaction)


    def _pipe_identifier_for_packet(self, packet):
        """
        Generates a hashable identifier that uniquely describes a given USB
        data stream. This is used as an index into packets_captured; and allows
        us to separate transactions that belong to e.g. different endpoints on
        different devices.

        This supports transfers that are interleaved with other transfers; as a
        transfer can be time-sliced with other transfers as long as the endpoint /
        device are different.
        """

        # FIXME: this should have a bus-ID-alike

        # Compute the effective endpoint address.
        # Special case: always consider control requests as having address 0,
        # as the control endpoint considers its two directions part of the same pipe.
        if packet.endpoint_number == 0:
            endpoint_address = 0
        else:
            endpoint_address = packet.direction.to_endpoint_address(packet.endpoint_number)

        return (packet.device_address, endpoint_address)


    def flush_queued_packets(self, pipe_identifier):
        """ Flushes any queued packets, and emits a new transfer composed of them. """

        # Grab all of the packets from the relevant pipe.
        packets = self.packets_captured[pipe_identifier]

        # If we don't have any queued packets, we don't need to do anything. Abort.
        if not packets:
            return

        # Start a new packet capture.
        self.packets_captured[pipe_identifier] = []

        # Special case: if have just a setup packet,
        if self.packets[0].token is USBPacketID.SETUP:
            assert len(packets) == 1

            self.emit_packet(USBSetupTransfer(**self.packets[0]))
            return


        # Special case: if this is a control transaction, split off the
        # handshake packet before emitting it.
        if self.packets[0].endpoint_number == 0:

            if self.packets[-1].direction != self.packets[0].direction:
                handshake_packet = self.packets.pop()


    def packet_concludes_transfer(self, packet):
        """ Returns true iff a given packet must end a transfer. """

        # If this is a setup token packet, it always ends a transfer.
        if packet.token is USBPacketID.SETUP:
            pass


    def packet_starts_new_transfer(self, packet):
        """ Returns true iff a given packet must start a transfer. """

        pipe = self._pipe_identifier_for_packet(packet)

        # If we have a setup token, this has to start a new transfer.
        if packet.token is USBPacketID.SETUP:
            return True

        # If we don't have any captured packets, this must
        # start a new transaction.
        if not self.packets_captured[pipe]:
            return False

        # If this is a control endpoint packet, apply special rules.
        try:
            first_packet = self.packets_captured[pipe][0]

            # Any direction switch on a control endpoint means we're ending a transfer.
            direction_switch = (packet.direction != first_packet.direction)
            if (packet.endpoint_number == 0) and direction_switch:
                return True
        except KeyError:
            return False



    def consume_packet(self, packet):
        pass

