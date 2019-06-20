"""
USB types -- defines enumerations that describe standard USB types
"""

from enum import Enum, IntFlag, IntEnum

class USBDirection(IntEnum):
    """ Class representing USB directions. """
    OUT = 0
    IN = 1

    def is_in(self):
        return self is self.IN

    def is_out(self):
        return self is self.OUT

    @classmethod
    def from_request_type(cls, request_type_int):
        """ Helper method that extracts the direction from a request_type integer. """
        return cls(request_type_int >> 7)

    def token(self):
        """ Generates the token corresponding to the given direction. """
        return USBPacketID.IN if (self is self.IN) else USBPacketID.OUT

    def reverse(self):
        """ Returns the reverse of the given direction. """
        return self.OUT if (self is self.IN) else self.IN


class USBPIDCategory(IntFlag):
    """ Category constants for each of the groups that PIDs can fall under. """

    SPECIAL   = 0b00
    TOKEN     = 0b01
    HANDSHAKE = 0b10
    DATA      = 0b11

    MASK      = 0b11



class USBPacketID(IntFlag):
    """ Enumeration specifying all of the valid USB PIDs we can handle. """

    # Token group (lsbs = 0b01).
    OUT   = 0b0001
    IN    = 0b1001
    SOF   = 0b0101
    SETUP = 0b1101

    # Data group (lsbs = 0b11).
    DATA0 = 0b0011
    DATA1 = 0b1011
    DATA2 = 0b0111
    MDATA = 0b1111

    # Handshake group (lsbs = 0b10)
    ACK   = 0b0010
    NAK   = 0b1010
    STALL = 0b1110
    NYET  = 0b0110

    # Special group.
    PRE   = 0b1100
    ERR   = 0b1100
    SPLIT = 0b1000
    PING  = 0b0100

    # Flag representing that the PID seems invalid.
    PID_INVALID   = 0b10000
    PID_CORE_MASK = 0b01111


    @classmethod
    def from_byte(cls, byte, skip_checks=False):
        """ Creates a PID object from a byte. """

        # Convert the raw PID to an integer.
        pid_as_int = int.from_bytes(byte, byteorder='little')
        return cls.from_int(pid_as_int, skip_checks=skip_checks)


    @classmethod
    def from_int(cls, value, skip_checks=True):
        """ Create a PID object from an integer. """

        PID_MASK           = 0b1111
        INVERTED_PID_SHIFT = 4

        # Pull out the PID and its inverse from the byte.
        pid          = cls(value & PID_MASK)
        inverted_pid = value >> INVERTED_PID_SHIFT

        # If we're not skipping checks, 
        if not skip_checks:
            if (pid ^ inverted_pid) != PID_MASK:
                pid |= cls.PID_INVALID
        
        return cls(pid)


    @classmethod
    def from_name(cls, name):
        """ Create a PID object from a string representation of its name. """
        return cls[name]


    @classmethod
    def parse(cls, value):
        """ Attempt to create a PID object from a number, byte, or string. """

        if isinstance(value, bytes):
            return cls.from_byte(value)

        if isinstance(value, str):
            return cls.from_name(value)

        if isinstance(value, int):
            return cls.from_int(value)

        return cls(value)


    def category(self):
        """ Returns the USBPIDCategory that each given PID belongs to. """
        return USBPIDCategory(self & USBPIDCategory.MASK)


    def is_data(self):
        """ Returns true iff the given PID represents a DATA packet. """
        return self.category() is USBPIDCategory.DATA


    def is_token(self):
        """ Returns true iff the given PID represents a token packet. """
        return self.category() is USBPIDCategory.TOKEN


    def is_handshake(self):
        """ Returns true iff the given PID represents a handshake packet. """
        return self.category() is USBPIDCategory.HANDSHAKE


    def is_invalid(self):
        """ Returns true if this object is an attempt to encapsulate an invalid PID. """
        return (self & self.PID_INVALID)

    def direction(self):
        """ Get a USB direction from a PacketID. """

        if self is SOF:
            return None

        if self is SETUP or self is OUT:
            return USBDirection.OUT

        if self is IN:
            return USBDirection.IN



    def summarize(self):
        """ Return a summary of the given packet. """

        # By default, get the raw name.
        core_pid  = self & self.PID_CORE_MASK
        name = core_pid.name

        if self.is_invalid():
            return "{} (check-nibble invalid)".format(name)
        else:
            return name


class USBRequestRecipient(IntEnum):
    """ Enumeration that describes each 'recipient' of a USB request field. """

    DEVICE    = 0
    INTERFACE = 1
    ENDPOINT  = 2
    OTHER     = 3

    RESERVED  = 4

    @classmethod 
    def from_integer(cls, value):
        """ Special factory that correctly handles reserved values. """

        # If we have one of the reserved values; indicate so.
        if 4 <= value < 16:
            return cls.RESERVED

        # Otherwise, translate the raw value.
        return cls(value)


    @classmethod
    def from_request_type(cls, request_type_int):
        """ Helper method that extracts the type from a request_type integer. """
        SHIFT = 5
        MASK  = 0b11

        return cls.from_integer((request_type_int >> SHIFT) & MASK)


class USBRequestType(IntEnum):
    """ Enumeration that describes each possible Type field for a USB request. """

    STANDARD  = 0
    CLASS     = 1
    VENDOR    = 2
    RESERVED  = 3


    @classmethod
    def from_request_type(cls, request_type_int):
        """ Helper method that extracts the type from a request_type integer. """

        MASK  = 0b11111
        return cls(request_type_int & MASK)



