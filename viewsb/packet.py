"""
ViewSB core packet definition -- defines the core ViewSB packet, and some of the core analyzer products
"""

class ViewSBPacket:
    """
    Class that provides a base for all analysis results, as "packets" of displayable data.
    Not to be confused with raw USB Packets, which are a very specific type of packet involved herein.
    """


    def get_summary_fields(self):
        """ Returns a dictionary of fields suitable for display in a single-line of a USB analysis record.

        Keys included:
            timestamp -- The number of microseconds into the capture at which the given packet occurred.
            length -- The total length of the given packet, in bytes, or None if not applicable.
            dev_address -- The address of the relevant USB device.
            endpoint -- The number of the endpoint associated with the given capture.

            status -- None if the packet was expected or normal; or a description if the packet was abnormal or error-y.
            style -- Any style keywords that should be applied to the relevant row.

            summary -- A short string description of the relevant packet, such as "IN transaction" or "set address request".
            data_summary - A short string description of any data included, such as "address=3" or "AA BB CC DD EE ..."
        """
        raise NotImplementedError()


    def get_detail_fields(self):
        """ Returns a full set of 'detail' structures that attempt to break this packet down in full detail.

        Each entry in the list is a 2-tuple, with the first element being a table title, and the second element
        being a string-to-string dictionary that can be represented as a two-column table. 
        
        For example, this function might return:
            ('Setup Packet', {'Direction': 'OUT', 'Recipient': 'Device', 'Type': 'Standard', 
                              'Request': 'Get Descriptor (0x06)', 'Index:' 0, 'Value': 'Device Descriptor (0x100)', 
                              'Length': '18'  })
        """
        raise NotImplementedError()


    def get_raw_data(self):
        """ Returns a byte-string of raw data, suitable for displaying in a hex inspection field. """
