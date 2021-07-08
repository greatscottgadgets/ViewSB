"""
Decoders that fill in descriptor data onto relevant transfers
(e.g. GetDescriptor and SetDescriptor)


This file is part of ViewSB
"""

from construct import this, Bytes

import usb_protocol

from usb_protocol.types.descriptor import DescriptorFormat, DescriptorField, DescriptorNumber
from usb_protocol.types.descriptors.partial import DeviceDescriptor, ConfigurationDescriptor, InterfaceDescriptor
from usb_protocol.types.descriptors.partial import EndpointDescriptor, DeviceQualifierDescriptor, StringDescriptor

from .standard_requests import GetDescriptorRequest

from ..decoder import ViewSBDecoder, UnhandledPacket


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
    BINARY_FORMAT = DeviceDescriptor

    def get_name_for_class(self, decoded):

        try:
            triplet = decoded['bDeviceClass'], decoded['bDeviceSubclass'], decoded['bDeviceProtocol']
        except AttributeError:
            return ""

        # XXX: look up these in a big array
        if triplet == (0,0,0):
            return "composite"
        elif triplet == (255, 255, 255):
            return "vendor-specific"

        # XXX: temporary hardcoding
        if decoded['bDeviceClass'] == 3:
            return "HID"
        if decoded['bDeviceClass'] == 9:
            return "Hub"

        return "{}:{}:{}".format(decoded['bDeviceClass'], decoded['bDeviceSubclass'], decoded['bDeviceProtocol'])


    def summarize_data(self, summary_length_bytes=16):

        # FIXME: store the parsed data via validate(), don't read this multiple times
        decoded, length = self.get_decoded_descriptor(use_pretty_names=False)

        try:
            class_text = self.get_name_for_class(decoded)
            return "vid={:04x}, pid={:04x}, class={}".format(
                decoded['idVendor'],
                decoded['idProduct'],
                class_text)
        except (KeyError, TypeError, AttributeError):
            return super().summarize_data(summary_length_bytes)


class GetConfigurationDescriptorRequest(GetDescriptorRequest):

    DESCRIPTOR_NAME = "configuration"
    BINARY_FORMAT = ConfigurationDescriptor


    def validate(self):

        # Run any parent validation.
        super().validate()

        # Parse the configuration descriptor and its subordinates.
        self.parse_with_subordinates()



    def find_last_descriptor(self, descriptor_number, subordinate_number=None):
        """
        Returns the last (as in 'most recent') subordinate descriptor of the current type.

        Params:
            descriptor_number -- The descriptor number to search for.
            subordinate_number -- If provided, the search will be limited to only subordinates
                that occurred -before- the given subordinate index.
        """

        last_interface_descriptor = None

        # Iterate over each of our subordinates...
        for index, subordinate in enumerate(self.subordinates):

            # ... skipping anything that's not of the correct type.
            try:
                if subordinate['raw']['bDescriptorType'] != descriptor_number:
                    continue

            # If we can't parse this as a descriptor, return None.
            except TypeError:
                return None

            # If we don't occur before provided subordinate number, we're finished searching.
            if subordinate_number and index >= subordinate_number:
                break

            # And keep track of the last interface descriptor we've seen.
            last_interface_descriptor = subordinate['raw']

        return last_interface_descriptor



    def find_last_interface_descriptor(self, subordinate_number=None):
        """
        Returns the last (as in 'most recent') subordinate interface descriptor currently known.

        Params:
            subordinate_number -- If provided, the search will be limited to only subordinates
                that occurred -before- the given subordinate index.
        """

        return self.find_last_descriptor(GetInterfaceDescriptorRequest.get_descriptor_number(), subordinate_number)


    def summarize_data(self, summary_length_bytes=16):

        # FIXME: store the parsed data via validate(), don't read this multiple times
        decoded, length = self.get_decoded_descriptor(use_pretty_names=False)

        try:
            # FIXME: describe the type of interfaces?
            # FIXME: provide subordinate descriptor count
            return "{} interface(s)".format(decoded['bNumInterfaces'])
        except (KeyError, TypeError):
            return super().summarize_data(summary_length_bytes)



    def handle_data_remaining_after_decode(self, data, subordinate_number):
        """ Handle a configuration descriptor's subordinate descriptors. """

        if len(data) < 2:
            return (None, None, None, 0)

        descriptor_reported_length = data[0]
        descriptor_number          = data[1]

        # Look up the descriptor class that handles this subordinate descriptor.
        descriptor_class = GetDescriptorRequest.get_descriptor_class_for_descriptor_number(descriptor_number)

        # If we found a descriptor class, use it.
        if descriptor_class:
            decoded, bytes_decoded = descriptor_class.decode_data_as_descriptor(data, parent=self)
            raw, _ = descriptor_class.decode_data_as_descriptor(data, use_pretty_names=False,
                parent=self, subordinate_number=subordinate_number)
            return descriptor_class.get_descriptor_name(data, self), decoded, raw, bytes_decoded
        else:
            name = 'Subordinate # {}: descriptor #{}'.format(subordinate_number, descriptor_number)
            return name, data[:descriptor_reported_length], data[:descriptor_reported_length], descriptor_reported_length




class GetStringDescriptorRequest(GetDescriptorRequest):

    DESCRIPTOR_NAME = "string"
    BINARY_FORMAT = StringDescriptor

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
                entries.append((langid, usb_protocol.types.LANGUAGE_NAMES[langid]))
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


    def handle_data_remaining_after_decode(self, data, subordinate_number):
        """
        We don't specify the data to decode in the descriptor definition; instead,
        we read the string itself out of the left-over body. Do that here.
        """


        # If we have a string index, this is a real search for a string.
        if self.index:

            # Parse the data as a string.
            string = data.decode('utf-16', 'replace')

            # Parse the string descriptor.
            return ('utf-16 string', string, data, len(data))

        # If our index is zero, this is a list of supported languages.
        else:

            # And return a single-column table displaying the supported languages.
            return ('languages supported', self._get_supported_language_strings(data), data, len(data))


    def summarize_data(self, summary_length_bytes=32):

        # Get the string's data, following the two-byte header.
        string_payload = self.data[2:]

        if self.index:
            # HACK: We're cheating a bit, here. summary_length_bytes is supposed to be the length in bytes,
            # but here it makes more sense to trim based on the length of the decoded string.
            summary = string_payload.decode('utf-16', 'backslashreplace')
            continuation = '...' if len(summary) > summary_length_bytes else ''
            return "{}{}".format(summary[0:summary_length_bytes], continuation)
        else:
            return ', '.join(self._get_supported_language_strings(string_payload))


    def get_pretty_descriptor_name(self):

        # If this a real string descriptor request, render it accordingly
        if self.index:
            return super().get_pretty_descriptor_name()

        # otherwise, indicate the special type of string descriptor it is
        else:
            return "supported-language 'string' descriptor"


class GetInterfaceDescriptorRequest(GetDescriptorRequest):

    DESCRIPTOR_NAME = "interface"
    BINARY_FORMAT = InterfaceDescriptor


class GetEndpointDescriptorRequest(GetDescriptorRequest):

    DESCRIPTOR_NAME = "endpoint"
    BINARY_FORMAT = EndpointDescriptor


class GetDeviceQualifierDescriptorRequest(GetDescriptorRequest):

    DESCRIPTOR_NAME = "device qualifier"
    BINARY_FORMAT = DeviceQualifierDescriptor



class GetClassSpecificDescriptorRequest(GetDescriptorRequest):

    # Specialized descriptor information -- either these two fields should be overridden,
    # or matches_class_specifics should be,
    CLASS_NUMBER       = -1
    DESCRIPTOR_SUBTYPE = -1

    # Generic descriptor information.
    DESCRIPTOR_NAME = "class-specific"
    BINARY_FORMAT = DescriptorFormat(
            "bLength"             / DescriptorField("Length"),
            "bDescriptorType"     / DescriptorNumber(0x24),
            "bDescriptorSubtype"  / DescriptorField("Descriptor Subtype"),
            "Data"                / Bytes(this.bLength)
    )


    @classmethod
    def matches_class_specifics(cls, usb_class, subclass, protocol, subtype, is_interface):
        """
        Determines whether the given class handles the given class/subclass/protocol and
        descriptor subtype. Should be overridden in subordinate classes if CLASS_NUMBER
        and DESCRIPTOR_SUBTYPE aren't.
        """

        # Default implementation.
        return (usb_class == cls.CLASS_NUMBER) and (subtype == cls.DESCRIPTOR_SUBTYPE)


    @classmethod
    def find_specialized_descriptor(cls, data, interface_descriptor, subtype):
        """
        Finds any specialized ClassSpecificDescriptor request objects that correspond
        to the current interface -or- to the device's class, and the descriptor subtype.
        """

        # FIXME: read the device class, and set the usb_class/subclass/protocol here;
        # only defer to the interface descriptor if we have a composite device.
        if not interface_descriptor:
            return None
        else:
            usb_class = interface_descriptor['bInterfaceClass']
            subclass  = interface_descriptor['bInterfaceSubclass']
            protocol  = interface_descriptor['bInterfaceProtocol']
            is_device = False

        # Search all of our subclasses.
        for subcls in cls.__subclasses__():
            matches = subcls.matches_class_specifics(usb_class, subclass, protocol, subtype, is_device)
            if matches:
                return subcls

        return None


    @classmethod
    def _add_subtype_names(cls, decoded, bytes_parsed, specialized_class):

        decoded_descriptor_fields = list(decoded.keys())

        # Update the second entry (the class type) to be class-specific.
        if len(decoded_descriptor_fields) >= 2:
            descriptor_type_row = decoded_descriptor_fields[1]
            decoded[descriptor_type_row] = 'class-specific'

        # Update the third entry (the subclass type) to feature the subclass name.
        if len(decoded_descriptor_fields) >= 3:
            descriptor_subtype_row  = decoded_descriptor_fields[2]
            decoded[descriptor_subtype_row] = specialized_class.get_descriptor_name()

        return decoded, bytes_parsed




    @classmethod
    def decode_as_specialized_descriptor(cls, data, use_pretty_names, parent, subordinate_number):

        # If we don't have at least three bytes, we can't read the subtype. Abort.
        if len(data) < 3:
            return None

        # Otherwise, the subtype is always stored in the third byte.
        subtype_number = data[2]

        # If we don't have a parent descriptor to work with, we can't figure out which class we belong to.
        if not parent:
            return None

        # Find the interface associated with this descriptor.
        interface_descriptor = parent.find_last_interface_descriptor(subordinate_number)

        # If we have an interface descriptor, try to figure out a more appropriate class to parse this structure.
        specialized_class = cls.find_specialized_descriptor(data, interface_descriptor, subtype_number)

        # If we found a more specialized class, use it!
        if specialized_class:
            decoded = specialized_class.decode_data_as_descriptor(data, use_pretty_names, parent, subordinate_number)

            # If we're using pretty names, add the more-specific subtype names.
            if use_pretty_names:
                decoded = cls._add_subtype_names(*decoded, specialized_class)

            return decoded

        return None



    @classmethod
    def decode_data_as_descriptor(cls, data, use_pretty_names=True, parent=None, subordinate_number=None):

        import sys

        # If we're being called from the GetClassSpecificDescriptor generic 'placeholder' class,
        # try to specialize.
        if cls == GetClassSpecificDescriptorRequest:
            specialized = cls.decode_as_specialized_descriptor(data, use_pretty_names, parent, subordinate_number)

            if specialized:
                return specialized

        # Otherwise, pass this down the chain.
        return super().decode_data_as_descriptor(data, use_pretty_names, parent)
