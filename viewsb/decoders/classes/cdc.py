"""
Communications Device Class decoders

This file is part of ViewSB.
"""

from ..standard_descriptors import GetClassSpecificDescriptorRequest
from usb_protocol.types.descriptor import DescriptorFormat, DescriptorField, DescriptorNumber


class GetCDCHeaderRequest(GetClassSpecificDescriptorRequest):

    CLASS_NUMBER = 2
    DESCRIPTOR_SUBTYPE = 0

    DESCRIPTOR_NAME = "CDC header"
    BINARY_FORMAT = DescriptorFormat(
            "bLength"             / DescriptorField("Length"),
            "bDescriptorType"     / DescriptorNumber(0x24),
            "bDescriptorSubtype"  / DescriptorField("Descriptor subtype"),
            "bcdCDC"              / DescriptorField("CDC version")
    )


class GetCDCCallManagement(GetClassSpecificDescriptorRequest):

    CLASS_NUMBER = 2
    DESCRIPTOR_SUBTYPE = 1

    DESCRIPTOR_NAME = "CDC call management"
    BINARY_FORMAT = DescriptorFormat(
            "bLength"                 / DescriptorField("Length"),
            "bDescriptorType"         / DescriptorNumber(0x24),
            "bDescriptorSubtype"      / DescriptorField("Descriptor subtype"),
            "bmCapabilities"          / DescriptorField("Capabilities"),
            "bSubordinateInterface0"  / DescriptorField("Data Interface"),
    )


class GetCDCAbstractControlManagamentHeader(GetClassSpecificDescriptorRequest):

    CLASS_NUMBER = 2
    DESCRIPTOR_SUBTYPE = 2

    DESCRIPTOR_NAME = "CDC-ACM function"
    BINARY_FORMAT = DescriptorFormat(
            "bLength"             / DescriptorField("Length"),
            "bDescriptorType"     / DescriptorNumber(0x24),
            "bDescriptorSubtype"  / DescriptorField("Descriptor subtype"),
            "bCapabilties"        / DescriptorField("Capabilities")
    )


class GetCDCUnionDescriptor(GetClassSpecificDescriptorRequest):

    CLASS_NUMBER = 2
    DESCRIPTOR_SUBTYPE = 6

    DESCRIPTOR_NAME = "CDC union"
    BINARY_FORMAT = DescriptorFormat(
            "bLength"                 / DescriptorField("Length"),
            "bDescriptorType"         / DescriptorNumber(0x24),
            "bDescriptorSubtype"      / DescriptorField("Descriptor subtype"),
            "bControlInterface"       / DescriptorField("Control Interface"),
            "bSubordinateInterface0"  / DescriptorField("Data Interface"),
    )
