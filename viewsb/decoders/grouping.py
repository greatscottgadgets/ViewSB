"""
Core decoders that handle manipulation of standard USB packets.

Includes functionality for e.g. breaking packets into transfers / transactions.


This file is part of ViewSB
"""

import collections
from datetime import timedelta
from construct import *

from usb_protocol.types import USBPacketID

from ..decoder import ViewSBDecoder, UnhandledPacket
from ..packet import USBPacket, MalformedPacket, USBStartOfFrame, USBStartOfFrameCollection, \
    USBTokenPacket, USBHandshakePacket, USBDataPacket, \
    USBTransaction, USBSetupTransaction, USBDataTransaction, \
    USBSetupTransfer, USBDataTransfer, USBStatusTransfer, USBControlTransfer



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

    def _consume_sof_packet(self, packet):
        """ Consumes a start-of-frame. """
        self.emit_packet(USBStartOfFrame(**packet.__dict__))

    def _consume_token_packet(self, packet):
        """ Consumes a packet known to be a token packet. """

        fields = packet.__dict__.copy()

        # If our packet isn't the right length for a token, emit
        # a malformed packet.
        if len(packet.data) != self.TOKEN_PAYLOAD_LENGTH:
            self.emit_packet(MalformedPacket(**fields))
            return

        # Extract the device address, endpoint number, and CRC5.
        fields['device_address']  = fields['data'][0] & 0x7F
        fields['endpoint_number'] = (fields['data'][1] & 0x07) << 1 | fields['data'][0] >> 7
        fields['crc5']            = fields['data'][1] >> 3

        # Fill direction from PID.
        fields['direction'] = fields['pid'].direction()

        # Populate a USBTokenPacket with the relevant information...
        new_packet = USBTokenPacket(**fields)

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
        if packet.pid is USBPacketID.SOF:
            self._consume_sof_packet(packet)
        elif packet.pid.is_token():
            self._consume_token_packet(packet)
        elif packet.pid.is_handshake():
            self._consume_handshake_packet(packet)
        elif packet.pid.is_data():
            self._consume_data_packet(packet)


        # If we didn't have a strategy for consuming the given packet
        # fail out and don't consume the packet.
        else:
            raise UnhandledPacket()


class USBStartOfFrameConglomerator(ViewSBDecoder):
    """ Decoder filter that squishes SOFs into a single packet. """

    def __init__(self, analyzer):
        super().__init__(analyzer)

        # Create a list of contiguous SOFs observed.
        self._packets = []



    def _emit_queued_packets(self):
        """ Emit all of our conglomerated packets. """

        # If we don't have any conglomerated packets, there's nothing to do!
        if not self._packets:
            return


        # Otherwise, create a new collection wrapping all of our captured SOFs.
        fields_to_copy = self._packets[0].__dict__.copy()
        #fields_to_copy['subordinate_packets'] = self._packets
        self.emit_packet(USBStartOfFrameCollection(**fields_to_copy))

        # And start a new collection of queued packets.
        self._packets.clear()


    def consume_packet(self, packet):

        # If this is a SOF packet, bundle it into our collection.
        if isinstance(packet, USBStartOfFrame):
            self._packets.append(packet)
        else:
            self._emit_queued_packets()
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

        if self._first_captured() is None:
            return

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

        # Case 1: if this is a token packet, capture it.
        if isinstance(packet, USBTokenPacket):

            # If we already have packets captured, emit them indicating there's a sequence error.
            if self.packets_captured:
                was_control_request = (self.packets_captured[0].endpoint_number == 0)
                self.emit_transaction(sequence_error=was_control_request)

            self.packets_captured.append(packet)

        # Case 2: if this is a data packet, and it's following a token packet, capture it.
        elif isinstance(packet, USBDataPacket):

            sequence_error = not isinstance(self._last_captured(), USBTokenPacket)

            if sequence_error:
                self.emit_transaction(sequence_error=True)

            self.packets_captured.append(packet)

            if sequence_error:
                self.emit_transaction(sequence_error=True)

        # Case 3: if this is a handshake packet; and it's following a token, capture it and emit the transaction.
        elif isinstance(packet, USBHandshakePacket):

            sequence_error = not isinstance(self._first_captured(), USBTokenPacket)

            if sequence_error:
                self.emit_transaction(sequence_error=True)

            self.packets_captured.append(packet)
            self.emit_transaction(sequence_error=sequence_error)



class USBTransactionSpecializer(ViewSBDecoder):
    """
    Decoder that converts transactions into more-specific types of transactions.
    """

    INCLUDE_IN_ALL = True

    def can_handle_packet(self, packet):
        return type(packet) is USBTransaction


    def consume_packet(self, packet):

        fields = packet.__dict__.copy()

        # If we have a SETUP token, convert this to a SetupTransaction.
        if packet.token is USBPacketID.SETUP:
                specialized_type = USBSetupTransaction
        # If we have a DATA token, convert this to a DataTransaction.
        elif packet.token in (USBPacketID.IN, USBPacketID.OUT):
                specialized_type = USBDataTransaction
                fields['data'] = None

        # If it's any other kind of transaction, emit it directly.
        # FIXME: support things like ping?
        else:
            raise UnhandledPacket()


        # Specialize the packet into the given type.
        try:
            transaction = specialized_type(**packet.__dict__)
        except StreamError:
            transaction = MalformedPacket(**packet.__dict__)

        self.emit_packet(transaction)



class USBTransferGrouper(ViewSBDecoder):
    """ Decoder that converts sequences of consecutive/coherent transactions into transfers. """

    # Don't include this specializer in all; it's not complete.
    INCLUDE_IN_ALL = True


    def __init__(self, analyzer):
        super().__init__(analyzer)

        # Create a mapping of packets captured.
        # These can be non-contiguous, so
        self.packets_captured = collections.defaultdict(lambda : [])


    def can_handle_packet(self, packet):
        """ We can handle any non-special transaction. """
        return type(packet) in (USBSetupTransaction, USBDataTransaction)



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


    def _emit_data_transfer_from_packets(self, packets):
        """ Emits a data transfer with data copied from the given set of packets. """

        fields = packets[0].__dict__.copy()

        # Clear the data/handshake fields; the transfer type will populate these for us.
        fields['data']      = None
        fields['handshake'] = None
        fields['subordinate_packets'] = packets

        # And emit the relevant transfer.
        self.emit_packet(USBDataTransfer(**fields))


    def flush_queued_packets(self, pipe_identifier):
        """ Flushes any queued packets, and emits a new transfer composed of them. """

        status_packet = None

        # Grab all of the packets from the relevant pipe.
        packets = self.packets_captured[pipe_identifier]

        # If we don't have any queued packets, we don't need to do anything. Abort.
        if not packets:
            return

        # Start a new packet capture.
        self.packets_captured[pipe_identifier] = []

        # Special case: if have just a setup packet, emit it immediately as a
        if packets[0].token is USBPacketID.SETUP:
            assert len(packets) == 1
            self.emit_packet(USBSetupTransfer(**packets[0].__dict__))
            return

        # Special case: if this is a control transaction, split off the
        # handshake packet before emitting it.
        if packets[0].endpoint_number == 0:
            if packets[-1].direction != packets[0].direction:
                status_packet = packets.pop()

        # Emit a single data transfer containing all of our packets.
        self._emit_data_transfer_from_packets(packets)

        # If we captured a stauts packet; emit it.
        if status_packet:
            self._emit_data_transfer_from_packets([status_packet])



    def packet_starts_new_transfer(self, packet):
        """ Returns true iff a given packet must end a transfer. """

        pipe = self._pipe_identifier_for_packet(packet)

        # If this is a setup token packet, it always starts a new transfer.
        if packet.token is USBPacketID.SETUP:
            return True


        # If this is a control endpoint packet, apply special rules.
        try:
            first_packet = self.packets_captured[pipe][0]


            # Any direction switch on a control endpoint means we're ending a transfer.
            direction_switch = (packet.direction != first_packet.direction)
            if (packet.endpoint_number == 0) and direction_switch:
                return True
        except (KeyError, IndexError):
            return False


        return False



    def packet_concludes_transfer(self, packet):
        """ Returns true iff a given packet must start a transfer. """

        # XXX: Typically we'd consider a transfer complete if we see a short packet.
        # To know if we have a short packet, we need the maximum packet size of the endpoint.
        # Since we don't have that right now, just check if the size is not a multiple of any
        # of the maximum packet sizes.
        if (packet.data is not None) and (packet.handshake == USBPacketID.ACK):
            if len(packet.data) == 0 or (len(packet.data) % 8) != 0:
                return True

        pipe = self._pipe_identifier_for_packet(packet)

        # If this is a setup token packet, it always ends the transfer.
        # (Setup packets always exist by themselves.)
        if packet.token is USBPacketID.SETUP:
            return True

        return False


    def packet_seems_discontinuous(self, packet):
        """ Return True iff there's been sufficient delay since the previous packet. """

        pipe = self._pipe_identifier_for_packet(packet)

        if not self.packets_captured[pipe]:
            return False

        last_packet = self.packets_captured[pipe][-1]

        # For non-control endpoints, if more than 10 milliseconds have passed since the last packet,
        # heuristically start a new transfer.
        if (
            packet.endpoint_number != 0
            and (packet.timestamp - last_packet.timestamp) > timedelta(microseconds=10e3)
        ):
            return True


    def enqueue_packet(self, pipe, packet):
        """ Enqueues a given packet on the relevant pipe. """
        self.packets_captured[pipe].append(packet)


    def consume_packet(self, packet):

        pipe = self._pipe_identifier_for_packet(packet)

        # If this packet starts a transfer, flush the pipe first.
        if self.packet_starts_new_transfer(packet) or self.packet_seems_discontinuous(packet):
            self.flush_queued_packets(pipe)

        self.enqueue_packet(pipe, packet)

        # If this packet ends a transfer, flush the pipe after the enqueue.
        if self.packet_concludes_transfer(packet):
            self.flush_queued_packets(pipe)



class USBControlRequestGrouper(ViewSBDecoder):
    """ Decoder that groups sequences of transfers into control requests. """

    def __init__(self, analyzer):
        super().__init__(analyzer)

        # Create a mapping of packets captured.
        # These can be non-contiguous, so
        self.packets_captured = collections.defaultdict(lambda : [])


    def _pipe_identifier_for_packet(self, packet):
        """
        Generates a hashable identifier that uniquely describes a given USB
        control pipe. This is used as an index into packets_captured; and allows
        us to separate transactions that belong to different devices.

        This supports transfers that are interleaved with other transfers; as a
        control transfer can be time-sliced with other control transfers as long as
        the relevant devices are different.
        """

        # FIXME: this should have a bus-ID-alike
        return (packet.device_address,)


    def can_handle_packet(self, packet):
        """ This class only handles transfers on EP0. """

        # We only handle Setup/Data packets on EP0.
        if type(packet) not in (USBSetupTransfer, USBDataTransfer):
            return False
        else:
            return packet.endpoint_number == 0


    def emit_control_request(self, pipe_identifier):
        """ Emits a control request composed of any queued packets for the relevant pipe. """

        transfer = None

        # Grab all of the packets from the relevant pipe.
        packets = self.packets_captured[pipe_identifier]

        # If we don't have any queued packets, we don't need to do anything. Abort.
        if not packets:
            return

        # Get an alias to our setup stage.
        setup = packets[0]

        # Start a new packet capture.
        self.packets_captured[pipe_identifier] = []

        # If we only have a single packet, this can't be a full control request;
        # and if we don't start with a setup, this isn't valid. Emit a malformed packet.
        if len(packets) == 1 or not isinstance(setup, USBSetupTransfer):
            self.emit_packet(MalformedPacket(**packets[0].__dict__))
            return

        # If we have two packets; we have a setup stage and either a data or status stage.
        elif len(packets) == 2:

            # If we should have a data stage, interpret the second packet as a data stage.
            if setup.request_length:
                transfer = USBControlTransfer.from_subordinates(setup, packets[1], None)
            # Otherwise, interpret it as a status stage.
            else:
                transfer = USBControlTransfer.from_subordinates(setup, None, packets[1])

        # If we have three packets, we have all three stages.
        elif len(packets) == 3:
            transfer = USBControlTransfer.from_subordinates(*packets)
        else:
            raise ValueError("internal consistency: got a control request with too many stages!")

        # Emit the generated control transfer.
        self.emit_packet(transfer)


    def enqueue_packet(self, pipe, packet):
        """ Enqueues a given packet on the relevant pipe. """
        self.packets_captured[pipe].append(packet)


    def consume_packet(self, packet):

        pipe = self._pipe_identifier_for_packet(packet)
        packets_on_pipe = self.packets_captured[pipe]

        # If this is a SETUP transaction, always flush whatever came before us.
        if isinstance(packet, USBSetupTransaction):
            self.emit_control_request(pipe)

        # If the first packet in the queue isn't a SETUP, always emit our packet buffer.
        # After this line, we know that the first packet in the queue is either a setup
        # transfer, or the queue is empty.
        if packets_on_pipe and not isinstance(packets_on_pipe[0], USBSetupTransaction):
            self.emit_control_request(pipe)

        # Always enqueue the current packet.
        self.enqueue_packet(pipe, packet)

        # Case 1: we now have one packet; we merely need to wait for more packets.

        # Case 2: we now have two packets.
        if len(packets_on_pipe) == 2:

            # Grab the setup packet, which is our first packet.
            setup = packets_on_pipe[0]

            # Emit what we have if we don't expect further packets in the control transaction.
            # We don't expect packets if the most recent packet stalled; or if we have no data stage (length=0).
            if (packet.handshake is USBPacketID.STALL) or (not setup.request_length):
                self.emit_control_request(pipe)

        # Case 3: we have three packets -- and must have completed the control request. Emit.
        elif len(packets_on_pipe) == 3:
            self.emit_control_request(pipe)



