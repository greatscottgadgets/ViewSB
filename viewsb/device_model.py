"""
Generic USB device model -- used to store information known about a given device
and its components (e.g. configurations, interfaces, endpoints).

This is used so decoders can have a knowledge of the device that spans more than a
single transfer -- e.g. they can look up the strings that correspond to given indices.

This file is part of ViewSB.
"""



class DeviceModelMetaclass(type):
    """ Metaclass that allows the DeviceModel object to find subordinates using a DeviceModel[address] syntax. """

    def __getitem__(cls, key):
        """ Allow the slicing/indexing operator on DeviceModel to look up devices by address. """

        return cls._get_model_by_address(key)



class DeviceModel(metaclass=DeviceModelMetaclass):
    """
    Class representing our model of a USB device, which encapsulates our knowledge of the device --
    and accordinly any parser state associated with the given device.
    """

    # Dictionary that stores all of our known models, so they can be looked up
    # by address. The canonical way to get one of these is to use the indexing operator
    # on the DeviceModel class.
    KNOWN_DEVICES = {}


    def __init__(self, address):
        """
        Creates a new instance of a DeviceModel -- usually you want to let the DeviceModel class create these
        for you by accessing DeviceModel[address].
        """

        self.address = address

        # Start off with a clean-slate knowledge of the given device.
        self.reset()


    def reset(self):
        """ Clears all known information about the given device. """

        # Create empty dictionaries of configurations, interfaces, and endpoints.
        self.configurations = {}
        self.interfaces     = {}


    @classmethod
    def _get_model_by_address(cls, address):
        """ Returns the DeviceModel with the given address, creating one if necessary. """

        # If the class isn't aware of a device with this address, create one.
        if address not in cls.KNOWN_DEVICES:
            cls.KNOWN_DEVICES[address] = DeviceModel(address)

        return cls.KNOWN_DEVICES[address]

