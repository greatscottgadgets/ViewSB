"""
ViewSB core packet definitions -- defines the core ViewSB packet, and some of the core analyzer products


This file is part of ViewSB
"""

# pylint: disable=maybe-no-member,access-member-before-definition

import struct
import binascii
from enum import Flag, auto
from construct import BitStruct, BitsInteger, BitsSwapped, Bytewise, Byte, Int16ul

from usb_protocol.types import USBDirection, USBRequestType, USBRequestRecipient, USBPacketID


# XXX Temporary hack for __repr__.
print_depth = 0



class ViewSBStatus(Flag):
    """ Enumeration representing USB packet statuses. """

    # Flags that can be provided for each flag.
    OK      = auto()
    OKAY    = OK

    # Error and warning statuses.
    WARNING = auto()
    ERROR   = auto()

    # A communication was aborted before its expected completion.
    ABORTED_INNER = auto()

    ABORTED = ABORTED_INNER | ERROR


class ViewSBPacket:
    """
    Class that provides a base for all analysis results, as "packets" of displayable data.
    Not to be confused with raw USB Packets, which are a very specific type of packet involved herein.
    """

    # The fields specific to this class. These are usually accessed using get_fields, which returns
    # the fields defined in the current or any parent class.
    FIELDS = {'timestamp', 'bus_number', 'device_address', 'endpoint_number', 'direction', 'status', 'style',
        'data', 'summary', 'data_summary', 'subordinate_packets'}

    # Data format. If a subclass overrides this with a construct Struct or BitStruct, that class
    # can call `parse_data` to automatically parse its data payload.
    DATA_FORMAT = None


    @classmethod
    def get_fields(cls):
        """ Defines the fields that make up this packet. """

        fields = set()

        # Build a list of all fields in the given class and all parent classes.
        # The simplest way to do this is just to grab all of the FIELDS properties in the method resolution order.
        for relevant_class in cls.mro():
            if hasattr(relevant_class, 'FIELDS'):
                fields |= relevant_class.FIELDS

        # Otherwise, extend the class with our local fields.
        return fields


    def __init__(self, **kwargs):
        """ Default constructor for a generic ViewSB packet. """

        # Validate that we have a timestamp.
        if 'timestamp' not in kwargs:
            raise ValueError("every ViewSB packet must have a timestamp!")

        # Populate our fields for from the arguments passed in.
        for field in self.get_fields():
            setattr(self, field, kwargs[field] if (field in kwargs) else None)

        if self.style is None:
            self.style = ""

        # If no subordinate packets were provided, convert that to an empty list.
        if self.subordinate_packets is None:
            self.subordinate_packets = []

        # Validate the data we've taken in.
        self.validate()


    def validate(self):
        """
        Validates the object's internal fields, normalizing data where necessary, and raises a ValueError (or similar)
        if any fields contain values that are invalid or unable to be normalized.
        """
        pass


    def parse_data(self, overwrite=False):
        """
        Parses the given packet's data using its DATA_FORMAT property, and uses the results to
        populate its fields.

        Args:
            overwrite -- If true, fields with the same name as DATA_FORMAT fields will always be overwritten
                with the parsed value. If false, they will be overwritten only if their value is None.'

        Returns: the DATA_FORMAT parser results, in case we need to capture any left-over fields
        """

        # Parse the data into fields.
        parsed = self.DATA_FORMAT.parse(self.data)

        # Iterate over each of the class's fields, checking if we can pull data
        # in from the parsed object.
        for field in self.get_fields():

            # Skip all fields starting with _ as private.
            if field.startswith('_'):
                continue

            # If we already have a value for the given field, and we're not in overwrite,
            # skip the relevant field.
            if not overwrite and (getattr(self, field) is not None):
                continue

            # Finally, if we have a value for the new field, accept it.
            if hasattr(parsed, field):
                setattr(self, field, parsed[field])

        # Finally, return the parser results.
        return parsed


    def parse_field_as_type(self, field_name, as_type, required=True):
        """ Ensures that a local packet field is a USBPacketID object; converting if necessary. """

        if not hasattr(self, field_name):
            if required:
                raise ValueError("{} expects a {} field".format(type(self).__name__, field_name))
            else:
                return

        if getattr(self, field_name) is None:
            if required:
                raise ValueError("{} packets require a valid {} in their {} field".format(
                    type(self).__name__, as_type.__name__, field_name))
            else:
                return

        # If the type has a parse method; use it.
        # Otherwise, call the type's constructor with the relevant value.
        if hasattr(as_type, 'parse'):
            conversion = as_type.parse
        else:
            conversion = as_type

        # Parse the current value as a PID.
        current_value = getattr(self, field_name)
        setattr(self, field_name, conversion(current_value))


    def parse_field_as_pid(self, field_name, required=True):
        """ Ensures that a local packet field is a USBPacketID object; converting if necessary. """
        self.parse_field_as_type(field_name, USBPacketID, required=required)


    def parse_field_as_direction(self, field_name, required=True):
        """ Ensures that a local packet field is a USBPacketID object; converting if necessary. """
        self.parse_field_as_type(field_name, USBDirection, required=required)


    def get_summary_fields(self):
        """ Returns a dictionary of fields suitable for display in a single-line of a USB analysis record.

        Strings can use prompt_toolkit style format specifications.

        Keys included:
            timestamp -- The number of microseconds into the capture at which the given packet occurred.
            length -- The total length of the given packet, in bytes, or None if not applicable.
            device_address -- The address of the relevant USB device, or None if not applicable.
            endpoint -- The number of the endpoint associated with the given capture, or None if not applicable.
            is_in -- True for an IN-associated packet; out for an OUT-associated packet; and None for no packet.

            status -- None if the packet was expected or normal; or a description if the packet was abnormal or error-y.
            style -- Any style keywords that should be applied to the relevant row.

            summary -- A short string description of the relevant packet, such as "IN transaction" or "set address request".
            data_summary - A short string description of any data included, such as "address=3" or "AA BB CC DD EE ..."
        """

        return {
            'timestamp':       self.timestamp,
            'length':          len(self.data) if self.data is not None else None,
            'bus_number':      self.bus_number,
            'device_address':  self.device_address,
            'endpoint':        self.endpoint_number,
            'is_in':           self.direction,
            'status':          self.summarize_status(),
            'style':           self.style,
            'summary':         self.summarize(),
            'data_summary':    self.summarize_data()
        }


    def get_style(self):
        """ Returns any style tags that should be placed on the given entry. """
        return self.style


    def generate_summary(self):
        """ Generates a very-short summary of the given packet; used if no summary is provided. """

        if self.direction is None:
            return "packet"
        else:
            return "IN packet" if self.direction.is_in() else "OUT packet"


    def summarize(self):
        """ Returns a very-short summary of the given packet; e.g. "IN packet". """

        # If we have an existing summary field, return it.
        if self.summary:
            return self.summary
        else:
            return self.generate_summary()


    def summarize_data(self, summary_length_bytes=8):
        """  Returns a quick summary of the given packet's data. """

        # Return an empty string if no data is present.
        if not self.data:
            return ""

        # By default, grab a hex representation of the first 32 bytes.
        summary_hex = binascii.hexlify(self.data[0:summary_length_bytes]).decode('utf-8')

        # Return the hex data split into byte-pairs.
        raw_hex = ' '.join(summary_hex[i:i + 2] for i in range(0, len(summary_hex), 2))

        # Provide an ellipse if the data extends past what we're displaying.
        continuation = '...' if len(self.data) > summary_length_bytes else ''
        return "{}{}".format(raw_hex, continuation)


    def summarize_status(self):
        """ Returns a quick text summary of the packet's general result. """

        # FIXME: represent things like errors from the status field, here?
        return ""


    def get_detail_fields(self):
        """ Returns a full set of 'detail' structures that attempt to break this packet down in full detail.

        Each entry in the list is a 2-tuple, with the first element being a table title, and the second element
        being a string-to-string dictionary that can be represented as a two-column table.

        For example, this function might return:
            [('Setup Packet', {'Direction': 'OUT', 'Recipient': 'Device', 'Type': 'Standard',
                              'Request': 'Get Descriptor (0x06)', 'Index:' 0, 'Value': 'Device Descriptor (0x100)',
                              'Length': '18'  })]
        """
        return [(self.summarize(), {'Data': self.summarize_data(summary_length_bytes=16)})]


    def get_raw_data(self):
        """ Returns a byte-string of raw data, suitable for displaying in a hex inspection field. """

        if self.data:
            return bytes(self.data)
        else:
            return b''


    @staticmethod
    def _include_details_in_debug():
        """ Returns true iff the given packet's details should be included in its debug output. """


    def __repr__(self):
        """ Provide a quick, console-friendly representation of our data."""

        global print_depth

        summary = self.summarize_data()

        if summary:
            data_summary = " [{}]".format(self.summarize_data())
        else:
            data_summary = ""

        # Quick stab at some nice formatting for console output.
        description = "<{}: d{}:e{} {}{} {}>".format(
            type(self).__name__, self.device_address, self.endpoint_number,
            self.summarize(), data_summary, self.summarize_status())

        # Quick hack.
        print_depth += 1
        for subordinate in self.subordinate_packets:

            # If the given subordinate ends the printing block; i.e. it's the last one, or it has a block
            # of subordinates itself that are following, use an angle brace; otherwise, use a tee.
            ends_group = subordinate is self.subordinate_packets[-1] or subordinate.subordinate_packets
            box_char = "┗"  if ends_group else "┣"

            # Indent the block properly for the given print depth.
            indent = "\t" * print_depth

            description += "\n{}{}━{}".format(indent, box_char, subordinate)
        print_depth -=1

        return description


class USBPacket(ViewSBPacket):
    """ Class describing a raw USB packet. """

    FIELDS = {'pid', 'sync_valid'}


    def validate(self):
        # Parse the PID fields as PIDs.
        self.parse_field_as_pid('pid')


    def generate_summary(self):
        if self.pid is None:
            return "unknown packet"
        elif self.pid.is_data() and self.data is not None and len(self.data) == 0:
            return "zero-length packet"
        else:
            return "{} packet".format(self.pid.summarize())


    def get_raw_data(self):
        """
        For transaction-level ViewSBPackets, this method normally returns the raw data in the data stage,
        which is what a user is most likely interested in, but for raw USB packets and their specializations,
        it'll return every field of the packet except for SYNC and EOP.
        Since the fields vary with the kinds of packets, get_raw_data is implemented for those specializations,
        and this method defintion is only here for documentation.
        """
        return bytes()


    @classmethod
    def from_raw_packet(cls, raw_packet, **fields):
        """ Create a new USBPacket object from a raw set of packet data. """

        # Create a copy of the raw packet so we can work with it.
        data = raw_packet[:]

        # Extract the PID from the first byte of the packet.
        packet_id = USBPacketID.parse(data.pop(0))

        # Store the remainder of the packet as the packet's data;
        # and wrap this in our packet object.
        return cls(pid=packet_id, data=data, **fields)

    # TODO: detailed representation


class USBStartOfFrame(USBPacket):
    """ Class representing a USB start-of-frame (pseudo) packet. """
    pass


class USBStartOfFrameCollection(USBPacket):
    """ Collection of USB SOFs that have been amalgamated for sane display. """

    def summarize(self):
        return "{} start-of-frame markers".format(len(self.subordinate_packets))


class USBTokenPacket(USBPacket):
    """ Class representing a token packet. """

    FIELDS = {'crc5', 'crc_valid'}

    DATA_FORMAT = BitsSwapped(BitStruct(
        "device_address"  / BitsInteger(7),
        "endpoint_number" / BitsInteger(4),
        "crc5"            / BitsInteger(5),
    ))


    def validate(self):
        #parsed = self.parse_data()
        # TODO: validate crc5
        pass


    def generate_summary(self):
        return "{} token".format(self.pid.summarize())


    def summarize_data(self, summary_length_bytes=8):
        # NOTE: summary_length_bytes is ignored for a token packet.
        return "address={}, endpoint=0x{:02x}, direction={}".format(
                self.device_address, self.endpoint_number, self.direction)


    def get_detail_fields(self):

        fields = {
            'Length': '{} bytes'.format(len(self.get_raw_data())),
            'PID': '{} (0x{:02x})'.format(self.pid.name, self.pid.value),
            'Device': '0x{:02x}'.format(self.device_address),
            'Endpoint': '0x{:02x}'.format(self.endpoint_number),
            'CRC5': '0x{:02x}'.format(self.crc5)
        }

        return [(self.generate_summary(), fields)]


    def get_raw_data(self):
        # device_address, endpoint, and crc5 are included in self.data.
        return b''.join([bytes([self.pid]), self.data])


class USBDataPacket(USBPacket):
    """ Class representing a data packet. """

    FIELDS = {'crc16', 'crc_valid'}


    def validate(self):
        # TODO: validate crc16
        pass


    def generate_summary(self):
        return "{} bytes; {}".format(len(self.data), self.pid.summarize())


    def summarize_data(self, summary_length_bytes=8):

        if len(self.data) == 0:
            return "ZLP"
        else:
            return super().summarize_data(summary_length_bytes)


    def get_detail_fields(self):

        fields = {
            'Length': '{} bytes'.format(len(self.get_raw_data())),
            'PID': '{} (0x{:02x})'.format(self.pid.name, self.pid.value),
            'Data': self.summarize_data(summary_length_bytes=16),
            'CRC16': '0x{:04x}'.format(int.from_bytes(self.crc16, byteorder='little'))
        }

        return [(self.generate_summary(), fields)]


    def get_raw_data(self):
        return b''.join([bytes([self.pid]), self.data, self.crc16])


class USBHandshakePacket(USBPacket):
    """ Handshake packets contain only their PIDs. """

    def generate_summary(self):
        return self.pid.summarize()


    def get_detail_fields(self):

        fields = {
            'Length': '{} bytes'.format(len(self.get_raw_data())),
            'PID': '{} (0x{:02x})'.format(self.pid.name, self.pid.value)
        }

        return [(self.generate_summary(), fields)]


    def get_raw_data(self):
        return bytes([self.pid])


class USBStatusTransfer(USBHandshakePacket):
    """
    USB status transfers are very similar to handshakes -- they're just
    one level up the abstraction ladder. Re-use that code.
    """

    # `handshake` and `pid` should be the same for a status transfer.
    FIELDS = { 'handshake' }


class MalformedPacket(USBPacket):
    """ Class representing a generic malformed packet. """

    def validate(self):
        if self.status is None:
            self.status = 0

        self.style = "error exceptional"

        # Malformed packets are always a protocol error.
        #self.status |= ViewSBStatus.ERROR


    def generate_summary(self):
        if self.pid:
            return "{} packet; malformed".format(self.pid.summarize())
        else:
            return "invalid data ({} subpackets)".format(len(self.subordinate_packets))


    def summarize_status(self):
        """ Always summarize our status as an error. """
        return "*INV*"


class USBTransaction(ViewSBPacket):
    """
    Class describing a raw USB transaction, which is a representation of a TOKEN,
    optional DATA, and HANDSHAKE packet.
    """

    FIELDS = {'token', 'handshake', 'data_pid'}


    def validate(self):
        # Parse our token fields as PIDs.
        self.parse_field_as_pid('token')
        self.parse_field_as_pid('data_pid',  required=False)
        self.parse_field_as_pid('handshake', required=False)

    # TODO: representation

    def summarize(self):
        return "{} transaction".format(self.token.name)


    def summarize_status(self):
        if self.handshake:
            return "{}{}".format(self.handshake.name, super().summarize_status())

        else:
            return super().summarize_status()


    @property
    def stalled(self):
        return self.handshake == USBPacketID.STALL


    @stalled.setter
    def stalled(self, value):
        self.handshake = USBPacketID.STALL if value else USBPacketID.ACK


class USBTransfer(ViewSBPacket):
    """ Class describing a generic USB transfer, which is a collection of conceptually-grouped transfers. """

    FIELDS = {'pid', 'handshake'}


    def summarize(self):
        return "{}B {} unspecified transfer".format(len(self.data), self.direction.name)

    def validate(self):
        self.parse_field_as_pid('pid',       required=False)
        self.parse_field_as_pid('handshake', required=False)


class USBDataTransaction(USBTransaction):
    """ Class describing a data-carrying transaction. """

    FIELDS = { 'data_pid', 'handshake'}


    def validate(self):
        self.parse_field_as_pid('data_pid',  required=False)
        self.parse_field_as_pid('handshake', required=False)

        # If we don't have a handshake, grab the handshake from the last packet
        # in the transfer. # TODO: should this be the last packet?
        if self.handshake is None and self.subordinate_packets:
            self.handshake = self.subordinate_packets[-1].handshake

        # If we don't have a direction field, populate it from the first contained packet.
        if self.direction is None and self.subordinate_packets:
            self.direction = self.subordinate_packets[0].direction

        # If we have a data stage, use it to populate the data fields.
        if len(self.subordinate_packets) == 3:
            self.data     = self.data or self.subordinate_packets[1].data
            self.data_pid = self.data_pid or self.subordinate_packets[1].data_pid


    def summarize_status(self):
        return self.handshake.name


class USBDataTransfer(USBTransaction, USBTransfer):
    """ Class describing a sequence of logically grouped, data-carrying transfers. """

    FIELDS = {'pid_sequence_ok', 'handshake'}


    def summarize(self):
        if self.data:
            return "{}B {} transfer".format(len(self.data), self.direction.name)
        else:
            return "data-less {} transfer".format(self.direction.name)


    def validate(self):
        self.parse_field_as_pid('handshake', required=False)

        # If we don't have a handshake, grab the handshake from the last packet
        # in the transfer. # TODO: should this be the last packet?
        if self.handshake is None and self.subordinate_packets:
            self.handshake = self.subordinate_packets[-1].handshake

        # If we don't have a direction field, populate it from the first contained packet.
        if self.direction is None and self.subordinate_packets:
            self.direction = self.subordinate_packets[0].direction

        # If we don't have a populated data field, populate it.
        if self.data is None:
            self.data = bytearray()

            for packet in self.subordinate_packets:

                # Append the data of all transactions that actually have data to the data of the overall transfer.
                if isinstance(packet, USBDataTransaction):
                    if packet.data and packet.handshake == USBPacketID.ACK:
                        self.data.extend(packet.data)

        # TODO: validate PID sequence


class USBTransferFragment(USBTransfer):
    """
    Class representing a piece of USB data that was the result of an incomplete capture,
    or data error.
    """

    FIELDS = {'transfer_type'}


    def summarize(self):
        return "ORPHANED {}B {}-{} transfer".format(len(self.data), self.direction.name, self.pid.name)


class USBBulkTransfer(USBDataTransfer):

    def summarize(self):
        return "bulk {} transfer ({})".format(self.direction.name, len(self.data))


class USBInterruptTransfer(USBDataTransfer):

    def summarize(self):
        return "interrupt {} transfer ({})".format(self.direction.name, len(self.data))


class USBIsochronousTransfer(USBDataTransfer):

    def summarize(self):
        return "isochronous {} transfer ({})".format(self.direction.name, len(self.data))


class USBSetupTransaction(USBTransaction):
    """
    Class describing a USB setup transaction, which is a specialized transaction that
    contains metadata for a control transfer.
    """

    FIELDS = {
        'request_direction', 'request_type', 'recipient', 'request_number',
        'value', 'index', 'request_length', 'handshake'
    }

    # Define the data format for setup packets.
    DATA_FORMAT = BitStruct(
        "request_direction" / BitsInteger(1),
        "request_type"      / BitsInteger(2),
        "recipient"         / BitsInteger(5),
        "request_number"    / Bytewise(Byte),
        "value"             / Bytewise(Int16ul),
        "index"             / Bytewise(Int16ul),
        "request_length"    / Bytewise(Int16ul)
    )


    def validate(self):
        self.parse_data()
        self.parse_field_as_direction('request_direction')

        # Extract our stalled field from the data/handshake PIDs.
        self.stalled = (self.data_pid is USBPacketID.STALL) or (self.handshake is USBPacketID.STALL)


    @classmethod
    def from_setup_data(cls, setup_data, **fields):

        # Ensure our setup-data is byte compatible.
        setup_data = bytes(setup_data)

        # Break our setup data into its component pieces.
        request_type_composite, request, value, index, length = struct.unpack("<BBHHH", setup_data)

        # Parse the request type bytes.
        direction    = USBDirection.from_request_type(request_type_composite)
        request_type = USBRequestType.from_request_type(request_type_composite)
        recipient    = USBRequestRecipient.from_request_type(request_type_composite)

        if 'endpoint_number' not in fields:
            fields['endpoint_number'] = 0

        if 'token' not in fields:
            fields['token'] = USBPacketID.SETUP

        if 'handshake' not in fields:
            fields['handshake'] = USBPacketID.ACK

        # Generate the setup transaction from the extracted data.
        transaction = USBSetupTransaction(direction=USBDirection.OUT, request_direction=direction,
                request_type=request_type, request_number=request, recipient=recipient,
                value=value, index=index, request_length=length, data=setup_data, **fields)
        return transaction


    def summarize(self):
        return "control request setup transaction for {} request".format(self.request_direction.name)


    def summarize_data(self, summary_length_bytes=8):
        # NOTE: summary_length_bytes is ignored for a SETUP transaction.
        return "value={:04x} index={:04x} length={:04x}".format(self.value, self.index, self.request_length)


class USBSetupTransfer(USBSetupTransaction):
    """ Synonym for a USBSetupTransaction, as those contain only one real transaction.

    Technically, we can contain subordinate USBSetupTransactions that have transmission
    errors; so this is slightly semantically different in what you'd expect in
    subordinate_packets.
    """

    def summarize(self):
        return "control request setup transfer for {} request".format(self.request_direction.name)


class USBControlTransfer(USBTransfer):
    """ Class representing a USB control transfer. """

    FIELDS = {'request_type', 'recipient', 'request_number', 'value', 'index', 'request_length', 'stalled'}


    @classmethod
    def from_subordinates(cls, setup_transfer, data_transfer, status_transfer):
        """ Generates a USB Control Transfer packet from its subordinate transfers. """

        fields = {}

        additional_fields = ('timestamp', 'endpoint_number', 'device_address', 'recipient')
        fields_to_copy_from_setup = cls.FIELDS.union(additional_fields)

        # Copy each of our local fields from the Setup transaction.
        for field in fields_to_copy_from_setup:
            fields[field] = getattr(setup_transfer, field)

        # Set the overall direction to the direction indicated in the SETUP transaction.
        fields['direction'] = setup_transfer.request_direction

        # If we have a data transaction, then copy our data from it.
        if data_transfer:
            fields['data'] = data_transfer.get_raw_data()
        else:
            fields['data'] = None

        # Set the transfer to stalled if the handshake token is stalled.
        fields['stalled'] = \
            (status_transfer and status_transfer.handshake == USBPacketID.STALL) or \
            (data_transfer and data_transfer.handshake == USBPacketID.STALL)

        # Set our subordinate packets to the three packets we're consuming.
        subordinates = [setup_transfer, data_transfer, status_transfer]
        fields['subordinate_packets'] = [s for s in subordinates if s is not None]

        # Finally, return our instance.
        return cls(**fields)


    def validate(self):
        self.parse_field_as_type('request_type', USBRequestType, required=True)
        self.parse_field_as_type('recipient', USBRequestRecipient, required=True)
        self.parse_field_as_direction('direction', required=True)

        # FIXME: validate our fields!

        # Set up our style.
        # FIXME: display error statuses as well
        if self.stalled:
            self.style = "exceptional"
        else:
            self.style = None


    def summarize(self):
        return "{} {} request #{} to {}".format(self.request_type.name, self.direction.name, self.request_number, self.recipient.name)


    def summarize_status(self):
        # FIXME: display error statuses, as well
        if self.stalled:
            return "STALL"
        else:
            return "ACK"
