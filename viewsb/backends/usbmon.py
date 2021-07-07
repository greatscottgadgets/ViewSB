"""
USB packet capture file backend


This file is part of ViewSB
"""

import errno
import struct

from datetime import timedelta
from enum import Enum

import usb_protocol

from usb_protocol.types import USBDirection, USBRequestRecipient, USBRequestType, USBPacketID, USBTransferType

from ..backend import ViewSBBackend, FileBackend
from ..packet import USBSetupTransfer, USBDataTransfer, USBStatusTransfer, USBControlTransfer, \
     USBBulkTransfer, USBInterruptTransfer, USBIsochronousTransfer, USBTransferFragment


class TransferType(Enum):
    ISOCHRONOUS = 0
    INTERRUPT   = 1
    CONTROL     = 2
    BULK        = 3

    def associated_data_transfer_type(self):
        """
        Returns the USBTransfer packet type most closely associated to the _payload_
        section of the provided transfer.
        """

        packet_types = {
            self.ISOCHRONOUS: USBIsochronousTransfer,
            self.INTERRUPT:   USBInterruptTransfer,
            self.CONTROL:     USBDataTransfer,
            self.BULK:        USBBulkTransfer,
        }
        return packet_types[self]

    def to_usb_transfer_type(self):
        """ Returns the USBTransferType that's equivalent to this USBMon transfer type. """
        return USBTransferType[self.name]


class EventType(Enum):
    """ Enumeration of the event-type flags used by USBmon. """
    SUBMISSION  = b'S'
    CALLBACK    = b'C'
    ERROR       = b'E'


# pylint: disable=no-member
class USBMonEvent:
    """ Class representing a USBMon event packet. """

    SHORT_HEADER_LENGTH = 48
    SHORT_HEADER_FORMAT = "<QcBBBHccQIiIIBBHHH"
    SHORT_HEADER_FIELD_NAMES = [
        "urb_tag", "event_type", "transfer_type", "endpoint_address", "device_address", "bus_number",
        "flag_setup", "flag_data", "timestamp_sec", "timestamp_microseconds", "status",
        "length", "length_captured", "request_type_or_error_count", "request_number_or_desc_number",
        "value", "index", "request_length"
    ]

    def __init__(self, **properties):
        """ Creates a new Event packet with the given list of properties."""

        # Absorb each of our properties.
        for name, value in properties.items():
            setattr(self, name, value)

        self.data = None


    def apply_data(self, data):
        """ Accepts a set of external data to become our data. """
        self.data = data


    def get_setup_data(self):
        """ Returns the event, construed as a USB setup packet. """

        # Squish the packets in our event back into a setup packet.
        # This is cleaner than extracting it from the packet, again.
        return struct.pack("<BBHHH", self.request_type_or_error_count,
            self.request_number_or_desc_number, self.value, self.index, self.request_length)



    @classmethod
    def from_raw_packet(cls, data):
        """ Parses a block of data into a dictionary representing a USBMon event. """

        if len(data) == cls.SHORT_HEADER_LENGTH:

            # Parse the event description...
            raw_metadata = struct.unpack(cls.SHORT_HEADER_FORMAT, data)

            # ... convert it to a dictionary, given appropriate names.
            properties = dict(zip(cls.SHORT_HEADER_FIELD_NAMES, raw_metadata))

        else:
            raise NotImplementedError("parsing full-size usbmon headers isn't yet supported")

        # Do some limited type conversions on the properties.
        properties['transfer_type']   = TransferType(properties['transfer_type'])
        properties['event_type']      = EventType(properties['event_type'])
        properties['direction']       = USBDirection.from_endpoint_address(properties['endpoint_address'])
        properties['endpoint_number'] = usb_protocol.types.endpoint_number_from_address(properties['endpoint_address'])

        # Finally, create the relevant event.
        return cls(**properties)


class USBMonBackend(ViewSBBackend):
    """
    Class that handles pcap data. Should not be instantiated directly;
    rather, instantiate one of its subclasses.
    """

    def __init__(self):
        """ Create our new backend object. """

        ViewSBBackend.__init__(self)

        # Create an empty mapping that will store pending URBs; indexed by tag.
        self.pending_urbs = {}


    def read_data(self, length):
        """ Attempts to read packet data from the relevant device. """
        raise NotImplementedError("usbmon parser must implement `read_data`!")


    def handle_data(self, data):
        """ Handle read and parsing of data from USBMon (or its capture file). """
        event_handlers = {
            EventType.SUBMISSION: self._handle_submission_event,
            EventType.CALLBACK: self._handle_callback_event,
            EventType.ERROR: self._handle_error_event,
        }
        event = USBMonEvent.from_raw_packet(data)

        # Read the data segment that follows the event header, if one is around,
        # and add it to our event.
        data = self.read_data(event.length_captured)
        event.apply_data(data)

        # Execute the correct sub-handler for the given event.
        event_handler = event_handlers[event.event_type]
        event_handler(event)


    def _handle_submission_event(self, event):
        """ Called when an URB is submitted to the Linux kernel. """

        # Add the submitted URB to our list of pending URBs.
        self.pending_urbs[event.urb_tag] = event


    def _handle_callback_event(self, callback):
        """ Called when the kernel considers an URB complete. """

        # Try to find the URB the callback is with respect to.
        try:
            submission = self.pending_urbs.pop(callback.urb_tag)
        except KeyError:
            submission = None

        # We have three general cases:

        # 1) This is completion of a control transfer; we'll need to
        #    build a control transfer object for the given event.
        if callback.transfer_type is TransferType.CONTROL:

            # If we have all the data we need to do that, do so:
            if submission:
                transfer = self._generate_control_transfer_for_events(submission, callback)

            # Otherwise, we have an orphaned event.
            else:
                transfer = self._generate_orphaned_transfer_for_event(callback)


        # 2) This is the completion of an OUT transfer. In most cases, we'll want
        #    to update the submitted transfer with our completion status.
        elif callback.direction.is_out():

            # If we have a submission to base things on, use that.
            if submission:

                # Copy the vital stats from the callback to the original URB.
                submission.status = callback.status
                submission.length_captured = callback.length_captured

                # And submit the original URB for transfer-ization.
                transfer = self._generate_data_transfer_for_event(submission)

            # If we have a OUT packet with both status and data, use that.
            # This would be unusual; but it'd make sense that this could be
            # generated e.g. in response to an interrupt or isochronous endpoint.
            elif callback.data or (not callback.length):
                transfer = self._generate_data_transfer_for_event(callback)

            # Otherwise, we have an orphaned event -- we don't know what data
            # was sent -- we only have some minimal context. Ideally, we'd generate
            # an orphaned fragment, here.
            else:
                transfer = self._generate_orphaned_transfer_for_event(callback)


        # 3) This is the completion of an IN transfer. This can be either a response
        #    to a submitted transfer; or it can be e.g. a packet coming in on a interrupt
        #    endpoint; whose URB submission is invisible to us.
        else:

            # An IN event should have all of the relevant data and status included in its
            # callback event; so we should be able to just ignore the missing submission.
            transfer = self._generate_data_transfer_for_event(callback)


        # Emit the generated packet.
        self.emit_packet(transfer)


    def _handle_error_event(self, event):
        """ Called when the kernel believes an error has occurred processing an URB. """

        # FIXME: handle!
        print(event)


    def _get_timestamp_for_event(self, event):
        """ Returns the timestamp for a given URB event. """

        # FIXME: is this right?
        return timedelta(microseconds=event.timestamp_microseconds)


    def _generate_data_transfer_for_event(self, event, stall=None):
        """ Generates a data transfer that encapsulates for the given event. """

        common_fields = self._common_packet_fields_for_event(event)

        # Override the handshake if we have to.
        if stall is not None:
            common_fields['handshake'] = USBPacketID.STALL if stall else USBPacketID.ACK

        # Convert the
        packet_type = event.transfer_type.associated_data_transfer_type()
        return packet_type(**common_fields)


    def _generate_orphaned_transfer_for_event(self, event):
        """ Generate an object that represents an 'orphaned' fragment of an event transfer. """
        return USBTransferFragment(**self._common_packet_fields_for_event(event))


    def _common_packet_fields_for_event(self, event):
        """
        Generates a dictionary with the USBTransaction fields most appropriate for
        the provided event. Intended to provide a base for customizations.
        """
        return {
            'timestamp': self._get_timestamp_for_event(event),
            'handshake': self._get_handshake_for_event(event),
            'endpoint_number': event.endpoint_number,
            'direction': event.direction,
            'device_address': event.device_address,
            'transfer_type': event.transfer_type.to_usb_transfer_type(),
            'data': event.data
        }


    def _generate_control_transfer_for_events(self, submission, callback):
        """ Generates a control transfer for the pair of submission and callback events. """

        # Generate the setup packet for our event, which will start the control transfer.
        setup_transfer = self._generate_setup_transfer_for_submission(submission)

        # Track the last packet direction, as it'll set the direction of the status stage.
        # We just issued a SETUP, so we last spoke OUT to the device.
        last_transfer_direction = USBDirection.OUT

        # Populate the submission object with the status results from the callback.
        submission.status = callback.status
        submission.length_captured = callback.length_captured

        # Look for data in either the submission or in the callback, depending on
        # whether this is an IN transfer or an OUT transfer. The kernel accepts data for
        # OUT transfers with the submission; and returns data for IN transfers with the callback.
        data_source = submission if setup_transfer.request_direction.is_out() else callback

        # If we have a populated data stage, generate a data transfer for it.
        if data_source.data:

            # If this is an IN request, and we've stalled, stall at the data phase.
            data_stall = (callback.status and callback.direction.is_in())
            data_transfer = self._generate_data_transfer_for_event(data_source, data_stall)
            last_transfer_direction = data_transfer.direction
        else:
            data_stall = False
            data_transfer = None


        # Finally, if we didn't stall during the data stage, generate a status transfer.
        if not data_stall:
            handshake_transfer = self._generate_status_transfer(callback, last_transfer_direction)
        else:
            handshake_transfer = None

        # Build and return the control request.
        return USBControlTransfer.from_subordinates(setup_transfer, data_transfer, handshake_transfer)


    def _get_handshake_for_event(self, event):
        """ Returns the handshake PID most appropriate for the given usbmon status code. """

        # If the event indicates success, return ACK.
        if event.status == 0:
            return USBPacketID.ACK

        # If the event indicates a pipe error, this is a STALL.
        elif event.status == -errno.EPIPE:
            return USBPacketID.STALL

        # Otherwise, a data error happened; NAK.
        else:
            return USBPacketID.NAK


    def _generate_status_transfer(self, event, last_transfer_direction):
        """
        Returns a transfer that represents the status stage of the control transfer represented
        by this event.
        """
        handshake      = self._get_handshake_for_event(event)
        fields         = self._common_packet_fields_for_event(event)
        fields['data'] = None

        return USBStatusTransfer(pid=handshake, **fields)


    def _generate_setup_transfer_for_submission(self, submission):
        """ Returns a setup packet corresponding to given Control Submission event. """

        # Parse the composite request-type field.
        request_type_packed  = submission.request_type_or_error_count
        direction            = USBDirection.from_request_type(request_type_packed)
        request_type         = USBRequestType.from_request_type(request_type_packed)
        recipient            = USBRequestRecipient.from_request_type(request_type_packed)

        # Capture the common packet fields into a basis for the setup transfer.
        fields = self._common_packet_fields_for_event(submission)

        # Path the field's direction, as SETUP packets always are host->device / OUT.
        fields['direction']      = USBDirection.OUT

        # Copy over our SETUP-specific fields.
        fields['request_direction'] = direction
        fields['request_number']    = submission.request_number_or_desc_number
        fields['request_type']      = request_type
        fields['recipient']         = recipient
        fields['value']             = submission.value
        fields['index']             = submission.index
        fields['request_length']    = submission.request_length
        fields['data']              = submission.get_setup_data()
        fields['token']             = USBPacketID.SETUP
        fields['handshake']         = USBPacketID.ACK

        # ... and convert the fields into a USBSetupTransfer packet.
        return USBSetupTransfer(**fields)


class USBMonFileBackend(USBMonBackend, FileBackend):
    """
    Class that handles pcap data, read from a file; whether a special device file
    or a pre-captured pcap file.
    """

    UI_NAME = "usbmon"
    UI_DESCRIPTION = "the linux USB monitor (and files captured from it)"


    @staticmethod
    def add_options(parser):

        # Parse user input and try to extract our class options.
        parser.add_argument('--file', dest='filename', default='/dev/usbmon0',
            help="The file to read usbmon data from")


    # TODO: support modes other than compatibility mode?
    READ_CHUNK_SIZE = 48

    def __init__(self, filename):

        # Call both of our parent initializers with the appropriate arguments.
        USBMonBackend.__init__(self)
        FileBackend.__init__(self, filename)


    def read_data(self, length):
        return self.read(length)
