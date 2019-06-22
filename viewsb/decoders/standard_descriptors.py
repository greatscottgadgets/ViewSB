"""
Decoders that fill in descriptor data onto relevant transfers
(e.g. GetDescriptor and SetDescriptor)
"""

from ..decoder import ViewSBDecoder, UnhandledPacket

from .standard_requests import GetDescriptorRequest
from ..descriptor import DescriptorFormat, DescriptorField, DescriptorNumber


class DescriptorRequestDecoder(ViewSBDecoder):
    """ Protocol decoder for Stanard-type USB control requests. """


    def can_handle_packet(self, packet):

        # Handle only get descriptor requests.
        # TODO: handle set descriptor requests; but lol who uses those
        return type(packet) in (GetDescriptorRequest,)


    def consume_packet(self, packet):

        # Try to find a more specialized version of the given control request.
        specialized = GetDescriptorRequest.get_specialized_transfer(packet)

        # If we found one, emit it!
        if specialized:
            self.emit_packet(specialized)

        # Otherwise, raise UnhandledPacket so the analyzer can look for another handler.
        else:
            raise UnhandledPacket()


#
# Definitions of our various descriptors.
#

class GetDeviceDescriptorRequest(GetDescriptorRequest):

    DESCRIPTOR_NAME = "device"
    BINARY_FORMAT = DescriptorFormat(
            "bLength"             / DescriptorField("Length"),
            "bDescriptorType"     / DescriptorNumber(1),
            "bcdUSB"              / DescriptorField("USB Version"),
            "bDeviceClass"        / DescriptorField("Class"),
            "bDeviceSubclass"     / DescriptorField("Subclass"),
            "bDeviceProtocol"     / DescriptorField("Protocol"),
            "bMaxPacketSize"      / DescriptorField("EP0 Max Pkt Size"),
            "idVendor"            / DescriptorField("Vendor ID"),
            "idProduct"           / DescriptorField("Product ID"),
            "bcdDevice"           / DescriptorField("Device Version"),
            "iManufacturer"       / DescriptorField("Manufacturer Str"),
            "iProduct"            / DescriptorField("Product Str"),
            "iSerialNumber"       / DescriptorField("Serial Number"),
            "bNumConfigurations"  / DescriptorField("Configuration Count"),
    )
