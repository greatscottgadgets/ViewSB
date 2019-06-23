"""
ViewSB core packet definitions -- defines the core ViewSB packet, and some of the core analyzer products
"""

# pylint: disable=maybe-no-member,access-member-before-definition

import struct
import binascii

from enum import Flag, auto
from .usb_types import USBDirection, USBRequestType, USBRequestRecipient, USBPacketID


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

    FIELDS = {'timestamp', 'device_address', 'endpoint_number', 'direction', 'status', 'style',
        'data', 'summary', 'data_summary', 'subordinate_packets'}

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


    def parse_field_as_pid(self, field_name, required=True):
        """ Ensures that a local packet field is a USBPacketID object; converting if necessary. """

        if not hasattr(self, field_name):
            if required:
                raise ValueError("{} expects a {} field".format(type(self).__name__, field_name))
            else:
                return

        if getattr(self, field_name) is None:
            if required:
                raise ValueError("{} packets require a valid PID in their {} field".format(type(self).__name__, field_name))
            else:
                return

        # Parse the current value as a PID.
        current_value = getattr(self, field_name)
        setattr(self, field_name, USBPacketID.parse(current_value))


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
            'device_address':  self.device_address,
            'endpoint':        self.endpoint_number,
            'is_in':           self.direction,
            'status':          self.status,
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


    def summarize_data(self):
        """  Returns a quick summary of the given packet's data. """

        SUMMARY_LENGTH_BYTES = 8

        # Return an empty string if no data is present.
        if not self.data:
            return ""

        # By default, grab a hex representation of the first 32 bytes.
        summary_hex = binascii.hexlify(self.data[0:SUMMARY_LENGTH_BYTES]).decode('utf-8')

        # Return the hex data split into byte-pairs.
        raw_hex = ' '.join(summary_hex[i:i + 2] for i in range(0, len(summary_hex), 2))

        # Provide an ellipse if the data extends past what we're displaying.
        continuation = '...' if len(self.data) > SUMMARY_LENGTH_BYTES else ''
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
        return [(self.summarize(), {'Data': self.summarize_data()})]


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

        summary = self.summarize_data()

        if summary:
            data_summary = " [{}]".format(self.summarize_data())
        else:
            data_summary = ""

        # Quick stab at some nice formatting for console output.
        description =  "<{}: d{}:e{} {}{} {}>".format(
            type(self).__name__, self.device_address, self.endpoint_number,
            self.summarize(), data_summary, self.summarize_status())

        # Quick hack.
        for subordinate in self.subordinate_packets:

            box_char = "┗"  if (subordinate is self.subordinate_packets[-1]) else "┣"
            description += "\n\t {}━{}".format(box_char, subordinate)

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



    @classmethod
    def from_raw_packet(cls, raw_packet, **fields):
        """ Create a new USBPacket object from a raw set of packet data. """

        # Create a copy of the raw packet so we can work with it.
        data = raw_packet[:]
       
        # Extract the PID from the first byte of the packet.
        packet_id = USBPacketID.parse(data.pop(0))

        # Store generthe remainder of the packet as the packet's data;
        # and wrap this in our packet object.
        return cls(pid=packet_id, data=data, **fields)



    # TODO: detailed representation

class USBTokenPacket(USBPacket):
    """ Class representing a token packet. """

    FIELDS = {'crc5', 'crc_valid'}

    def validate(self):

        # Fill in our direction from our PID.
        self.direction = self.pid.direction().name

        # TODO: validate crc5

    def generate_summary(self):
            return "{} token".format(self.pid.summarize())

    def summarize_data(self):
            return "address={}, endpoint=0x{:02x}, direction={}".format(
                    self.device_address, self.endpoint_number, self.direction)


class USBDataPacket(USBPacket):
    """ Class representing a data packet. """

    FIELDS = {'crc16', 'crc_valid'}

    def validate(self):
        # TODO: validate crc16
        pass

    def generate_summary(self):
        return "{} bytes; {}".format(len(self.data), self.pid.summarize())

    def summarize_data(self):

        if len(self.data) == 0:
            return "ZLP"
        else:
            return super().summarize_data()




class USBHandshakePacket(USBPacket):
    """ Handshake packets contain only their PIDs. """

    def generate_summary(self):
        return self.pid.summarize()





class USBStatusTransfer(USBHandshakePacket):
    """ 
    USB status transfers are very similar to handshakes -- they're just
    one level up the abstraction ladder. Re-use that code.
    """

    pass


class MalformedPacket(USBPacket):
    """ Class representing a generic malformed packet. """

    def validate(self):

        if self.status is None:
            self.status = 0

        # Malformed packets are always a protocol error.
        #self.status |= ViewSBStatus.ERROR

    def generate_summary(self):
       if self.pid:
           return "{} packet; malformed".format(self.pid.summarize())
       else:
           return "malformed packet"


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
        return "{} packet".format(self.token.name)

    def summarize_status(self):
        if self.handshake:
            # FIXME: don't include this arrow, it's just stylish for now
            return "-> {}{}".format(self.handshake.name, super().summarize_status())

        else:
            return super().summarize_status()

    @property
    def stalled(self):
        return self.handshake == USBPacketID.STALL

    @stalled.setter
    def stalled(self, value):
        self.handshake = USBPacketID.STALL if value else USBPacketID.ACK


class USBTransfer(ViewSBPacket):
    """ Class describing a generic USB transfer, which is the a collection of conceptually-grouped transfers. """

    FIELDS = {'pid', 'handshake'}

    def summarize(self):
        return "{}B {} unspecified transfer".format(len(self.data), self.direction.name)

    def validate(self):
        self.parse_field_as_pid('pid',       required=False)
        self.parse_field_as_pid('handshake', required=False)



class USBDataTransaction(USBTransaction):
    """ Class describing a data-carrying transation. """

    FIELDS = {'data_pid', 'handshake'}

    def validate(self):
        self.parse_field_as_pid('data_pid',  required=False)
        self.parse_field_as_pid('handshake', required=False)


class USBDataTransfer(USBTransaction, USBTransfer):
    """ Class describing a sequence of logcially grouped, data-carrying transfers. """

    FIELDS = {'pid_sequence_ok', 'handshake'}

    def summarize(self):
        return "{}B {} transfer".format(len(self.data), self.direction.name)

    def validate(self):
        self.parse_field_as_pid('data_pid',  required=False)
        self.parse_field_as_pid('handshake', required=False)


class USBTransferFragment(USBTransfer):
    """ 
    Class representing a piece of USB data that was the result of an incomplete capture,
    or data error.
    """

    FIELDS = {'transfer_type'}

    def summarize(self):
        return "ORPHANED {}B {}-{} tranfer".format(len(self.data), self.direction.name, self.pid.name)


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

    def summarize_data(self):
        return "value={:04x} index={:04x} length={:04x}".format(self.value, self.index, self.request_length)

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



class USBSetupTransfer(USBSetupTransaction):
    """ Synonym for a USBSetupTransaction, as those contain only one real transaction. 
    
    Technically, we can contain subordinate USBSetupTransactions that have transmission
    errors; so this is slightly semantically different in what you'd expect in 
    subordinate_packets.
    """
    pass



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
            (status_transfer and status_transfer.pid == USBPacketID.STALL) or \
            (data_transfer and data_transfer.handshake == USBPacketID.STALL)

        # Set our subordinate packets to the three packets we're consuming.
        subordinates = [setup_transfer, data_transfer, status_transfer]
        fields['subordinate_packets'] = [s for s in subordinates if s is not None]

        # Finally, return our instance.
        return cls(**fields)


    def summarize(self):
        return "{} {} request #{} to {}".format(self.request_type.name, self.direction.name, self.request_number, self.recipient.name)


    def summarize_status(self):

        # FIXME: get rid of the stylish arrow
        if self.stalled:
            return "-> STALL"
        else:
            return "-> ACK"

    def validate(self):

        # FIXME: validate our fields
        pass
