"""
Functionality for working with USB descriptors.


This file is part of ViewSB
"""

import construct
from .packet import ViewSBPacket


class DescriptorFormat(construct.Struct):

    @staticmethod
    def _to_detail_dictionary(descriptor):
        result = {}

        # Loop over every entry in our descriptor context, and try to get a
        # fancy name for it.
        for key, value in descriptor.items():

            # Don't include any underscore-prefixed private members.
            if key.startswith('_'):
                continue

            # If there's no definition for the given key in our format, # skip it.
            if not hasattr(descriptor._format, key):
                continue

            # Try to apply any documentation on the given field rather than it's internal name.
            format_element = getattr(descriptor._format, key)
            detail_key = format_element.docs if format_element.docs else key

            # Finally, add the entry to our dict.
            result[detail_key] = value

        return result


    def parse(self, data, **context_keywords):
        """ Hook on the parent parse() method which attaches a few methods. """

        # Use construct to run the parse itself...
        result = super().parse(data, **context_keywords)

        # ... and then bind our static to_detail_dictionary to it.
        result._format = self
        result._to_detail_dictionary = self._to_detail_dictionary.__get__(result, type(result))

        return result


class DescriptorNumber(construct.Const):
    """ Trivial wrapper class that denotes a particular Const as the descriptor number. """

    def __init__(self, const):

        # If our descriptor number is an integer, instead of "raw",
        # convert it to a byte, first.
        if not isinstance(const, bytes):
            const = const.to_bytes(1, byteorder='little')

        # Grab the inner descriptor number represented by the constant.
        self.number = int.from_bytes(const, byteorder='little')

        # And pass this to the core constant class.
        super().__init__(const)

        # Finally, add a documentation string for the type.
        self.docs = "Descriptor Type"


    def _parse(self, stream, context, path):
        const_bytes = super()._parse(stream, context, path)
        return const_bytes[0]


    def get_descriptor_number(self):
        """ Returns this constant's associated descriptor number."""
        return self.number



class DescriptorField(construct.Subconstruct):
    """
    Construct field definition that automatically adds fields of the proper
    size to Descriptor definitions.
    """

    #
    # The C++-wonk operator overloading is Construct, not me, I swear.
    #

    # FIXME: these are really primitive views of these types;
    # we should extend these to get implicit parsing wherever possible
    USB_TYPES = {
        'b'   : construct.Optional(construct.Int8ul),
        'bcd' : construct.Optional(construct.Int16ul),  # Create a BCD parser for this
        'i'   : construct.Optional(construct.Int8ul),
        'id'  : construct.Optional(construct.Int16ul),
        'bm'  : construct.Optional(construct.Int8ul),
        'w'   : construct.Optional(construct.Int16ul),
    }

    @staticmethod
    def _get_prefix(name):
        """ Returns the lower-case prefix on a USB descriptor name. """
        prefix = []

        # Silly loop that continues until we find an uppercase letter.
        # You'd be aghast at how the 'pythonic' answers look.
        for c in name:

            # Ignore leading underscores.
            if c == '_':
                continue

            if c.isupper():
                break
            prefix.append(c)

        return ''.join(prefix)


    @classmethod
    def _get_type_for_name(cls, name):
        """ Returns the type that's appropriate for a given descriptor field name. """

        try:
            return cls.USB_TYPES[cls._get_prefix(name)]
        except KeyError:
            raise ValueError("field names must be formatted per the USB standard!")


    def __init__(self, description=""):
        self.description = description


    def __rtruediv__(self, field_name):
        field_type = self._get_type_for_name(field_name)

        # wew does construct make this look weird
        return (field_name / field_type) * self.description



class DescriptorTransfer(ViewSBPacket):
    """ Mix-in class for transfers whose data payloads can be interpreted as a single USB descriptor. """

    # Each descriptor should define a DescriptorFormat here.
    #
    # The format is defined by setting BINARY_FORMAT = DescriptorFormat(...). 
    # The DescriptorFormat initializer takes the same arguments as construct.Struct;
    # it's intended to be a thin wrapper around those objects.
    BINARY_FORMAT = DescriptorFormat(
            "bLength"             / DescriptorField("Length"),
            "bDescriptorType"     / DescriptorField("Descriptor Number")
    )
    DESCRIPTOR_NAME = None

    @classmethod
    def get_descriptor_number(cls):
        """ Returns the descriptor number for the given field. """

        for subconstruct in cls.BINARY_FORMAT.subcons:
            if hasattr(subconstruct, 'get_descriptor_number'):
                return subconstruct.get_descriptor_number()

        raise ValueError("a descriptor format was defined with no DescriptorNumber!")


    @classmethod
    def get_descriptor_class_for_descriptor_number(cls, descriptor_number):

        # Search each of the subclasses of the current class until we
        # find a class that matches the given descriptor.
        #
        # TODO: possibly just try parsing everything and catch the exceptions
        # when the consts don't match?
        #

        # ... and look up the descriptor with the given number.
        for subclass in cls.__subclasses__():
            if subclass.get_descriptor_number() == descriptor_number:

                # Invoke the transfer "copy constructor".
                return subclass

        return None


    @classmethod
    def get_specialized_transfer(cls, transfer, descriptor_number=None):

        # If we're not provided with a descriptor number, try to pull one
        # out of the relevant packet.
        if descriptor_number is None:
            try:
                raw_data = transfer.get_raw_data()
                descriptor_number = raw_data[1]
            except IndexError:
                return None

        # Fetch the descriptor class for the given number, and try to instantiate it.
        subclass = cls.get_descriptor_class_for_descriptor_number(descriptor_number)
        if subclass:
            return subclass(**transfer.__dict__)
        else:
            return None


    @classmethod
    def decode_data_as_descriptor(cls, data, use_pretty_names=True):
        """ 
        Decodes the given data as this descriptor; and returns a dictionary of fields,
        and the total number of bytes parsed.
        """

        if not data:
            return None, 0

        # FIXME: do we want to do this?
        descriptor_length = data[0]

        if len(data) < descriptor_length:
            descriptor_length = len(data)

        # Parse the descriptor packet's data using its binary format.
        # This gives us an object that has a description of the decoded descriptor data.
        # Say that five times fast.

        # FIXME: memoize this!
        parsed_data = cls.BINARY_FORMAT.parse(data)

        # If we don't want to prepare the descriptor for display, return it directly.
        if not use_pretty_names:
            return parsed_data, descriptor_length

        if hasattr(parsed_data, 'bDescriptorType') and cls.DESCRIPTOR_NAME:
            parsed_data.bDescriptorType = "{}".format(cls.DESCRIPTOR_NAME)

        # Convert that to a dictionary that represents a table.
        return parsed_data._to_detail_dictionary(), descriptor_length


    def get_decoded_descriptor(self, data=None, use_pretty_names=True):
        """ Parses this packet into descriptor information. """

        if data is None:
            data = self.get_raw_data()

        return self.decode_data_as_descriptor(data, use_pretty_names)


    def handle_data_remaining_after_decode(self, data):
        """ Called if data is remaining after our decode. If data remains after this call, this
        method will be called again, until there's no data or we return None for the 
        extracted table-or-string.

        Args:
            data -- The data left-over after a parse operation completes when
                    fetching detail fields.

        Returns:
            (description, table_or_string, bytes_parsed) -- A 3-tuple including
            a description of the structure parsed, the resultant decoder table
            and the number of bytes parsed.
        """
        return (None, None, 0)


    def get_detail_fields(self):
        """ Gets all of the detail fields for a given descriptor. """

        if not self.BINARY_FORMAT:
            return super().get_detail_fields()

        data = self.get_raw_data()

        if not data:
            return None

        # Read the expected length out of the descriptor before we do any parsing.
        expected_length = data[0]

        # Start off with a table list containing the decoded parent descriptor.
        table_or_string, bytes_parsed = self.get_decoded_descriptor(data)
        incomplete = "incomplete " if (expected_length > bytes_parsed) else ""
        table_list = [("{}{} descriptor".format(incomplete, self.DESCRIPTOR_NAME), table_or_string)]

        # While we are still getting descriptors, try to handle any left-over data.
        while table_or_string:

            # Clip off any data parsed.
            data = data[bytes_parsed:]

            # Call our "data remaining" callback.
            description, table_or_string, bytes_parsed = self.handle_data_remaining_after_decode(data)

            #If we were able to parse more from the remaining data, return it.
            if table_or_string:
                table_list.append((description, table_or_string))


        return table_list







