"""
Functionality for working with USB descriptors.
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
        'b'   : construct.Int8ul,
        'bcd' : construct.Int16ul,  # Create a BCD parser for this
        'i'   : construct.Int8ul,
        'id'  : construct.Int16ul,
        'bm'  : construct.Int8ul,
        'w'   : construct.Int16ul,
    }

    @staticmethod
    def _get_prefix(name):
        """ Returns the lower-case prefix on a USB descriptor name. """
        prefix = []

        # Silly loop that continues until we find an uppercase letter.
        # You'd be aghast at how the 'pythonic' answers look.
        for c in name:
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
    BINARY_FORMAT = None

    @classmethod
    def get_descriptor_number(cls):
        """ Returns the descriptor number for the given field. """

        for subconstruct in cls.BINARY_FORMAT.subcons:
            if hasattr(subconstruct, 'get_descriptor_number'):
                return subconstruct.get_descriptor_number()

        raise ValueError("a descriptor format was defined with no DesriptorNumber!")


    @classmethod
    def get_specialized_transfer(cls, transfer, descriptor_number=None):

        # Search each of the subclasses of the current class until we
        # find a class that matches the given descriptor.
        #
        # TODO: possibly just try parsing everything and catch the exceptions
        # when the consts don't match?
        #

        # If we're not provided with a descriptor number, try to pull one
        # out of the relevant packet.
        if descriptor_number is None:
            try:
                raw_data = transfer.get_raw_data()
                descriptor_number = raw_data[1]
            except IndexError:
                return None


        # ... and look up the descriptor with the given number.
        for subclass in cls.__subclasses__():
            if subclass.get_descriptor_number() == descriptor_number:

                # Invoke the transfer "copy constructor".
                return subclass(**transfer.__dict__)

        return None


    def get_decoded_descriptor(self):

        # Parse the descriptor packet's data using its binary format.
        # This gives us an object that has a description of the decoded descriptor data.
        # Say that five times fast.
        parsed_data = self.BINARY_FORMAT.parse(self.get_raw_data())

        # Convert that to a dictionary that represents a table.
        return parsed_data._to_detail_dictionary()


    def get_detail_fields(self):

        if self.BINARY_FORMAT:
            detail_dictionary = self.get_decoded_descriptor()
            return [("{} descriptor".format(self.DESCRIPTOR_NAME), detail_dictionary)]
        else:
            super().get_detail_fields()







