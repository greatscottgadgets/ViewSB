"""
Functionality for working with USB descriptors.


This file is part of ViewSB
"""

from usb_protocol.types.descriptor import DescriptorFormat, DescriptorField
from construct.core import ConstError, ConstructError

from .packet import ViewSBPacket


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
        """ Returns the descriptor number for the given class. """

        for subconstruct in cls.BINARY_FORMAT.subcons:
            if hasattr(subconstruct, 'get_descriptor_number'):
                return subconstruct.get_descriptor_number()

        raise ValueError("a descriptor format was defined with no DescriptorNumber!")


    @classmethod
    def get_descriptor_name(cls, data=None, parent=None):
        """ Returns the descriptor name for the given class. """

        return cls.DESCRIPTOR_NAME


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
    def decode_data_as_descriptor(cls, data, use_pretty_names=True, parent=None, subordinate_number=0):
        """
        Decodes the given data as this descriptor; and returns a dictionary of fields,
        and the total number of bytes parsed.
        """

        if not data:
            return None, 0

        # The descriptor's length is always the first element of the descriptor; but truncate
        # if we don't have a whole one.
        descriptor_length = data[0]
        if len(data) < descriptor_length:
            descriptor_length = len(data)

        # Parse the descriptor packet's data using its binary format.
        # This gives us an object that has a description of the decoded descriptor data.
        # Say that five times fast.

        # FIXME: memoize this?
        parsed_data = cls.BINARY_FORMAT.parse(data)

        # If we don't want to prepare the descriptor for display, return it directly.
        if not use_pretty_names:
            return parsed_data._to_detail_dictionary(use_pretty_names=False), descriptor_length

        if hasattr(parsed_data, 'bDescriptorType') and cls.DESCRIPTOR_NAME:
            parsed_data.bDescriptorType = "{}".format(cls.DESCRIPTOR_NAME)

        # Convert that to a dictionary that represents a table.
        return parsed_data._to_detail_dictionary(), descriptor_length



    def get_decoded_descriptor(self, data=None, use_pretty_names=True):
        """ Parses this packet into descriptor information. """

        if data is None:
            data = self.get_raw_data()

        try:
            return self.decode_data_as_descriptor(data, use_pretty_names)
        except ConstError as error:
            errorParts = str(error).split('\n')
            what = error.path.split('->')[1].strip() if error.path else "error"
            self.parsed = {what: errorParts[1]}
        except ConstructError:
            pass
        return None, 0

    def handle_data_remaining_after_decode(self, data, subordinate_number):
        """ Called if data is remaining after our decode. If data remains after this call, this
        method will be called again, until there's no data or we return None for the
        extracted table-or-string.

        Args:
            data -- The data left-over after a parse operation completes when
                    fetching detail fields.

        Returns:
            (description, table_or_string, raw_dictionary, bytes_parsed) -- A 5-tuple including
            a description of the structure parsed, the resultant decoder table for printing, a raw
            dictionary-like object mapping decoder fields to raw values, and the number of bytes parsed.
        """
        return (None, None, None, 0)



    def parse_with_subordinates(self):
        """ Parses the given descriptor object, along with any subordinate descriptors attached, if appropriate. """

        if not self.BINARY_FORMAT:
            return

        data = self.get_raw_data()

        if not data:
            return None

        # Read the expected length out of the descriptor before we do any parsing.
        expected_length = data[0]

        # Decode our own descriptor.
        table_or_string, bytes_parsed = self.get_decoded_descriptor(data)
        incomplete = "incomplete " if (expected_length > bytes_parsed) else ""

        # Store that descriptor any create empty lists of subordinates.
        if table_or_string:
            self.parsed = table_or_string
        self.subordinates = []

        # While we are still getting descriptors, try to handle any left-over data.
        while table_or_string:
            from construct import ValidationError

            # Keep track of our position in the subordinate array.
            subordinate_number = len(self.subordinates)

            # Clip off any data parsed.
            data = data[bytes_parsed:]

            try:
                # Call our "data remaining" callback.
                description, table_or_string, raw, bytes_parsed = \
                    self.handle_data_remaining_after_decode(data, subordinate_number)
            except ValidationError:
                break

            #If we were able to parse more from the remaining data, return it.
            if table_or_string:

                self.subordinates.append({
                    'description': description,
                    'decoded': table_or_string,
                    'raw':     raw,
                })



    def get_detail_fields(self):
        """ Gets all of the detail fields for a given descriptor. """

        if not self.BINARY_FORMAT:
            return super().get_detail_fields()

        # If we don't have a parsed version of this class, try to parse it.
        if not hasattr(self, 'parsed'):
            self.parse_with_subordinates()

        # If we still don't have a parsed version, we have nothing to display. Abort.
        if not hasattr(self, 'parsed'):
            return None

        # Otherwise, create a list of descriptor tables.
        table_list = [(self.DESCRIPTOR_NAME, self.parsed)]

        # Convert our lists of subordinates and descriptions into entires in our list...
        for subordinate in self.subordinates:
            table_list.append((subordinate['description'], subordinate['decoded']))

        # ... and return the list.
        return table_list

