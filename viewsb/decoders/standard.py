"""
Core decoders that handle manipulation of standard USB packets.

Includes functionality for e.g. breaking packets into transfers / transactions.
"""

import bitstruct

from ..decoder import ViewSBDecoder, UnhandledPacket
from ..packet import USBPacket, MalformedPacket, USBTokenPacket, USBHandshakePacket, \
     USBDataPacket, USBTransaction


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





