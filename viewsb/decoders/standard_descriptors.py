"""
Decoders that fill in descriptor data onto relevant transfers
(e.g. GetDescriptor and SetDescriptor)


This file is part of ViewSB
"""

import construct
from construct import this

from .standard_requests import GetDescriptorRequest

from .. import usb_types
from ..decoder import ViewSBDecoder, UnhandledPacket
from ..descriptor import DescriptorFormat, DescriptorField, DescriptorNumber


class DescriptorRequestDecoder(ViewSBDecoder):
    """ Protocol decoder for Standard-type USB control requests. """


    def can_handle_packet(self, packet):

        # Handle only get descriptor requests.
        # TODO: handle set descriptor requests; but lol who uses those
        return type(packet) in (GetDescriptorRequest,)


    def consume_packet(self, packet):

        # Read the requested device number out of our packet.
        descriptor_number = packet.descriptor_number

        # Try to find a more specialized version of the given control request.
        specialized = GetDescriptorRequest.get_specialized_transfer(packet, descriptor_number=descriptor_number)

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

    def get_name_for_class(self, decoded):

        try:
            triplet = decoded.bDeviceClass, decoded.bDeviceSubclass, decoded.bDeviceProtocol
        except AttributeError:
            return ""

        # XXX: look up these in a big array
        if triplet == (0,0,0):
            return "composite"
        elif triplet == (255, 255, 255):
            return "vendor-specific"

        # XXX: temporary hardcoding
        if decoded.bDeviceClass == 3:
            return "HID"
        if decoded.bDeviceClass == 9:
            return "Hub"

        return "{}:{}:{}".format(decoded.bDeviceClass, decoded.bDeviceSubclass, decoded.bDeviceProtocol)


    def summarize_data(self):

        # FIXME: store the parsed data via validate(), don't read this multiple times
        decoded, length = self.get_decoded_descriptor(use_pretty_names=False)

        try:
            class_text = self.get_name_for_class(decoded)
            return "vid={:04x}, pid={:04x}, class={}".format(
                decoded.idVendor,
                decoded.idProduct,
                class_text)
        except (KeyError, TypeError, AttributeError):
            return super().summarize_data()


class GetConfigurationDescriptorRequest(GetDescriptorRequest):

    DESCRIPTOR_NAME = "configuration"
    BINARY_FORMAT = DescriptorFormat(
            "bLength"             / DescriptorField("Length"),
            "bDescriptorType"     / DescriptorNumber(2),
            "wTotalLength"        / DescriptorField("Length including subordinates"),
            "bNumInterfaces"      / DescriptorField("Interface count"),
            "bConfigurationValue" / DescriptorField("Configuration number"),
            "iConfiguration"      / DescriptorField("Description string"),
            "bmAttributes"        / DescriptorField("Attributes"),
            "bMaxPower"           / DescriptorField("Max power Consumption"),
    )


    def summarize_data(self):

        # FIXME: store the parsed data via validate(), don't read this multiple times
        decoded, length = self.get_decoded_descriptor(use_pretty_names=False)

        try:
            # FIXME: describe the type of interfaces?
            # FIXME: provide subordinate descriptor count
            return "{} interface".format(decoded.bNumInterfaces)
        except KeyError:
            return super().summarize_data()


    def handle_data_remaining_after_decode(self, data):
        """ Handle a configuration descriptor's subordinate descriptors. """

        if len(data) < 2:
            # FIXME: indicate a malformed packet!
            return (None, None, 0)

        descriptor_reported_length = data[0]
        descriptor_number          = data[1]

        # Look up the descriptor class that handles this subordinate descriptor.
        descriptor_class = GetDescriptorRequest.get_descriptor_class_for_descriptor_number(descriptor_number)

        # If we found a descriptor class, use it.
        if descriptor_class:
            decoded, bytes_decoded = descriptor_class.decode_data_as_descriptor(data)
            return descriptor_class.DESCRIPTOR_NAME, decoded, bytes_decoded
        else:
            name = 'Subordinate Descriptor #{}'.format(descriptor_number)
            return name, data[:descriptor_reported_length], descriptor_reported_length




class GetStringDescriptorRequest(GetDescriptorRequest):

    DESCRIPTOR_NAME = "string"
    BINARY_FORMAT = DescriptorFormat(
            "bLength"             / DescriptorField("Length"),
            "bDescriptorType"     / DescriptorNumber(3),
    )

    def get_decoded_descriptor(self, data=None):

        # If we weren't provided, data, use all of the packet's data.
        if data is None:
            data = self.get_raw_data()

        # If we have a string descriptor, parse this normally.
        if self.index:
            return super().get_decoded_descriptor(data)

        # Otherwise, this is a list of supported languages.
        # Return a summary of it; and let the "additional data" handler parse each language ID.
        else:

            # Every language entry is two bytes; compute how many entries we have...
            language_entries = int(len(data) / 2)

            # ... and return just how many entries there are, consuming the two-byte header.:W
            return {'language entries': str(language_entries)}, 2



    def get_supported_language_info(self, data=None):

        # If we have no data, grab the packet's raw data.
        if data is None:
            data = self.get_raw_data()

        entries = []
        while data:

            # Grab two bytes of the packet; which indicates a single language ID.
            raw_langid = data[0:2]

            # Parse it into a number...
            langid = int.from_bytes(data[0:2], byteorder='little')

            # Add the language to our list.
            try:
                entries.append((langid, usb_types.LANGUAGE_NAMES[langid]))
            except KeyError:
                entries.append((langid, None))

            # Move on to the next language ID.
            data = data[2:]

        return entries


    def _get_supported_language_strings(self, data=None):
        """ Returns a list of supported language names. """

        strings = []

        # Convert each supported language into a list of description rows.
        language_pairs = self.get_supported_language_info(data)
        for langid, name in language_pairs:
            if name is not None:
                strings.append("{} (#{:02x})".format(name, langid))
            else:
                strings.append("language #0x{:02x}".format(langid))

        return strings


    def handle_data_remaining_after_decode(self, data):
        """
        We don't specify the data to decode in the descriptor definition; instead,
        we read the string itself out of the left-over body. Do that here.
        """


        # If we have a string index, this is a real search for a string.
        if self.index:

            # Parse the data as a string.
            string = data.decode('utf-16', 'replace')

            # Parse the string descriptor.
            return ('utf-16 string', string, len(data))

        # If our index is zero, this is a list of supported languages.
        else:

            # And return a single-column table displaying the supported languages.
            return ('languages supported', self._get_supported_language_strings(data), len(data))


    def summarize_data(self):

        # Get the string's data, following the two-byte header.
        string_payload = self.data[2:]

        if self.index:
            return string_payload.decode('utf-16', 'replace')
        else:
            return ', '.join(self._get_supported_language_strings(string_payload))


    def get_descriptor_name(self):

        # If this a real string descriptor request, render it accordingly
        if self.index:
            return super().get_descriptor_name()

        # otherwise, indicate the special type of string descriptor it is
        else:
            return "supported-language 'string' descriptor"


class GetInterfaceDescriptorRequest(GetDescriptorRequest):

    DESCRIPTOR_NAME = "interface"
    BINARY_FORMAT = DescriptorFormat(
            "bLength"             / DescriptorField("Length"),
            "bDescriptorType"     / DescriptorNumber(4),
            "bInterfaceNumber"    / DescriptorField("Interface number"),
            "bAlternateSetting"   / DescriptorField("Alternate setting"),
            "bNumEndpoints"       / DescriptorField("Endpoints included"),
            "bInterfaceClass"     / DescriptorField("Class"),
            "bInterfaceSubclass"  / DescriptorField("Subclass"),
            "bInterfaceProtocol"  / DescriptorField("Protocol"),
            "iInterface"          / DescriptorField("String index"),
    )


class GetEndpointDescriptorRequest(GetDescriptorRequest):

    DESCRIPTOR_NAME = "endpoint"
    BINARY_FORMAT = DescriptorFormat(
            "bLength"             / DescriptorField("Length"),
            "bDescriptorType"     / DescriptorNumber(5),
            "bEndpointAddress"    / DescriptorField("EndpointAddress"),
            "bmAttributes"        / DescriptorField("Attributes"),
            "wMaxPacketSize"      / DescriptorField("Maximum Packet Size"),
            "bInterval"           / DescriptorField("Polling interval"),
    )


class GetDeviceQualifierDescriptorRequest(GetDescriptorRequest):

    DESCRIPTOR_NAME = "device qualifier"
    BINARY_FORMAT = DescriptorFormat(
            "bLength"             / DescriptorField("Length"),
            "bDescriptorType"     / DescriptorNumber(6),
            "bcdUSB"              / DescriptorField("USB Version"),
            "bDeviceClass"        / DescriptorField("Class"),
            "bDeviceSubclass"     / DescriptorField("Subclass"),
            "bDeviceProtocol"     / DescriptorField("Protocol"),
            "bMaxPacketSize0"     / DescriptorField("EP0 Max Pkt Size"),
            "bNumConfigurations"  / DescriptorField("Configuration Count"),
            "_bReserved"          / construct.Optional(construct.Const(b"\0"))
    )



class GetClassSpecificDescriptorRequest(GetDescriptorRequest):

    DESCRIPTOR_NAME = "class-specific"
    BINARY_FORMAT = DescriptorFormat(
            "bLength"             / DescriptorField("Length"),
            "bDescriptorType"     / DescriptorNumber(0x24),
            "bDescriptorSubtype"  / DescriptorField("Descriptor Subtype"),
            "data"                / construct.Bytes(this.bLength)
    )
