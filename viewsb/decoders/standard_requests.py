"""
Protocol decoder for standard USB Requests.


This file is part of ViewSB
"""


# pylint: disable=maybe-no-member,access-member-before-definition


from usb_protocol.types import USBRequestType, USBRequestRecipient

from ..decoder import ViewSBDecoder, UnhandledPacket
from ..packet import USBControlTransfer
from ..descriptor import DescriptorTransfer


class StandardControlRequest(USBControlTransfer):
    """ Base class for all USB standard control request definitions. """

    # Provide this number in order to select which request number you handle.
    REQUEST_NUMBER = None

    # And specify the contexts in which you can handle things.
    # Assume we handle the given request on a device-level, if nothing else is
    # provided.
    RECIPIENTS_HANDLED = [USBRequestRecipient.DEVICE]

    # If this is set to your request name (e.g. "GET STATUS"), this method
    # will automatically populate a short summary.
    REQUEST_NAME = None


    @classmethod
    def handles_request(cls, request):
        """ Default function for determining whether this class can decode the given standard request."""
        return \
            (request.request_number == cls.REQUEST_NUMBER) and \
            (request.recipient in cls.RECIPIENTS_HANDLED)


    @classmethod
    def from_control_transfer(cls, transfer):
        """ Creates a new instance of the current class from the given control transfer. """

        # Trivial "copy constructor".
        return cls(**transfer.__dict__)


    @classmethod
    def get_specialized_request(cls, transfer):
        """
        Consumes the provided transfer, and returns a more specialized version,
        or none if we can't generate a more specialized version.
        """

        # Iterate over all of our subclasses, until we find one that handles this
        # type of request
        for subclass in cls.__subclasses__():
            if subclass.handles_request(transfer):
                return subclass.from_control_transfer(transfer)

        # If we weren't able to handle the provided packet, raise UnhandledPacket,
        # so the analyzer looks for a different decoder.
        return None


    def summarize(self):

        # Provide a request-name based summary, if one's provided; otherwise fall back to the predecessor.
        if self.REQUEST_NAME:
            return "standard {} request ({})".format(self.REQUEST_NAME, self.direction.name.lower())
        else:
            return super().summarize()


class StandardRequestDecoder(ViewSBDecoder):
    """ Protocol decoder for Standard-type USB control requests. """

    def can_handle_packet(self, packet):

        # Handle only standard requests.
        return \
            (type(packet) == USBControlTransfer) and \
            (packet.request_type is USBRequestType.STANDARD)


    def consume_packet(self, packet):

        # Try to find a more specialized version of the given control request.
        specialized = StandardControlRequest.get_specialized_request(packet)

        # If we found one, emit it!
        if specialized:
            self.emit_packet(specialized)

        # Otherwise, raise UnhandledPacket so the analyzer can look for another handler.
        else:
            raise UnhandledPacket()


class GetStatus(StandardControlRequest):
    REQUEST_NUMBER = 0
    REQUEST_NAME = "GET STATUS"

    FIELDS = set()

    def validate(self):
        self.new_address = self.value

    def summarize(self):
        return "requesting {} status".format(self.recipient.name.lower())


class SetAddressRequest(StandardControlRequest):
    REQUEST_NUMBER = 5
    REQUEST_NAME = "SET ADDRESS"
    FIELDS = { "new_address" }

    def validate(self):
        self.new_address = self.value

    def summarize(self):
        return "requesting device use address {}".format(self.new_address)


class SetConfigurationRequest(StandardControlRequest):
    REQUEST_NUMBER = 9
    REQUEST_NAME = "SET ADDRESS"
    FIELDS = { "configuration_number" }

    def validate(self):
        self.configuration_number = self.value

    def summarize(self):
        return "requesting device switch to configuration {}".format(self.configuration_number)



class GetDescriptorRequest(StandardControlRequest, DescriptorTransfer):
    """ A request to read a standard descriptor. """

    REQUEST_NUMBER = 6
    REQUEST_NAME = "GET DESCRIPTOR"

    FIELDS = { "descriptor_number", "descriptor_index" }

    def validate(self):

        # Split the value field into a type and index.
        self.descriptor_number  = self.value >> 8
        self.descriptor_index = self.value & 0xFF


    def get_pretty_descriptor_name(self):
        """
        Returns the descriptor name; or a short-stand-in-summary when the name is
        unavailable or misleading (e.g. for a 'get string descriptor, index 0').
        """
        if self.DESCRIPTOR_NAME:
            return "{} descriptor".format(self.DESCRIPTOR_NAME)
        else:
            return  "descriptor number {}".format(self.descriptor_number)


    def summarize(self):
        return "requesting {} bytes of {} #{}".format(
            self.request_length, self.get_pretty_descriptor_name(), self.descriptor_index)


    def __repr__(self):


        # XXX: for fancy demos, only
        import io
        import tableprint

        string = super().__repr__()


        formatted = io.StringIO()
        summary_fields, total_bytes = self.get_decoded_descriptor()

        if summary_fields:
            tableprint.table(list(summary_fields.items()), out=formatted, width=40)


        string = "{}\n{}".format(string, formatted.getvalue())
        return string
