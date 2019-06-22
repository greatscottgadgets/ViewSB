"""
Protocol decoder for standard USB Requests.
"""


# pylint: disable=maybe-no-member,access-member-before-definition



from ..decoder import ViewSBDecoder, UnhandledPacket
from ..packet import USBControlTransfer
from ..usb_types import USBRequestType, USBRequestRecipient
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

        # If we weren't able to handle the provied, packet, raise UnhandledPacket,
        # so the analyzer looks for a different decoder.
        return None


    def summarize(self):

        # Provide a request-name based summary, if one's provided; otherwise fall back to the predecessor.
        if self.REQUEST_NAME:
            return "standard {} request ({})".format(self.REQUEST_NAME, self.direction.name.lower())
        else:
            return super().summarize()


class StandardRequestDecoder(ViewSBDecoder):
    """ Protocol decoder for Stanard-type USB control requests. """

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



class GetDescriptorRequest(StandardControlRequest, DescriptorTransfer):
    """ A request to read a standard descriptor. """

    REQUEST_NUMBER = 6
    REQUEST_NAME = "GET DESCRIPTOR"

    DESCRIPTOR_NAME = None

    FIELDS = { "descriptor_type", "descriptor_index" }

    def validate(self):

        # Split the value field into a type and index.
        self.descriptor_type  = self.value >> 8
        self.descriptor_index = self.value & 0xFF


    # XXX: this shouldn't be printing this >.>
    def __repr__(self):
        import io
        import tableprint

        formatted = io.StringIO()

        formatted.write(super().__repr__() + "\n")

        if self.BINARY_FORMAT:
            to_print = self.get_decoded_descriptor()
            tableprint.table(list(to_print.items()), out=formatted, width=22)

        return formatted.getvalue()


    def summarize(self):

        if self.DESCRIPTOR_NAME:
            descriptor_text = "{} descriptor".format(self.DESCRIPTOR_NAME)
        else:
            descriptor_text = "descriptor number {}".format(self.descriptor_type)

        return "requesting {} bytes of {}, index {}".format(
            self.request_length, descriptor_text, self.descriptor_index)
