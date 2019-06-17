"""
USBProxy backend for ViewSB
"""

from facedancer import FacedancerUSBApp
from facedancer.USBProxy import USBProxyDevice, USBProxyFilter
from facedancer.filters.standard import USBProxySetupFilters

from ..backend import ViewSBBackend


class ViewSBProxyObserver(USBProxyFilter):
    """ 
    USBProxy filter that observes all packets passing through it, without modification.
    Submits the relevant data to ViewSB for processing.
    """

    def __init__(self, backend):

        # Store a reference to our parent backend, so we can submit USB data via it.
        self.backend = backend

        # Mark ourselves as having no packet pending.
        self.pending_packet = None


    def filter_control_in(self, req, data, stalled):
        return req, data, stalled

    def filter_control_out(self, req, data):
        return req, data

    def handle_out_request_stall(self, req, data, stalled):
        return req, data, stalled

    def filter_in(self, ep_num, data):
        return ep_num, data

    def filter_out(self, ep_num, data):
        return ep_num, data

    def handle_out_stall(self, ep_num, data, stalled):
        return ep_num, data, stalled



class USBProxyBackend(ViewSBBackend):
    """ Capture backend that captures packets as they're proxied from device to device. """


    def __init__(self, vendor_id, product_id, additional_filters=None):
        """
        Creates a new USBProxy instance that captures all passed packets to ViewSB.

        Args:
            vendor_id -- The vendor ID of the device to be proxied.
            product_id -- The product ID of the device to be proxied.
            additional_filters -- A list of any additional filters to be installed in the proxy stack.
        """

        # Create the backend USBProxy instance that will perform our captures...
        facedancer_app = FacedancerUSBApp()
        self.proxy = USBProxyDevice(facedancer_app, idVendor=vendor_id, idProduct=product_id)

        # ... add the necessary filters to perform our magic...
        self.proxy.add_filter(ViewSBProxyObserver(self))
        self.proxy.add_filter(USBProxySetupFilters(self.proxy))

        # ... and add any other filters passed in.
        if additional_filters:
            for additional_filter in additional_filters:
                self.proxy.add_filter(additional_filter)

        # Set up our connection to the device-to-be-proxied.
        self.proxy.connect()


    def run_capture(self):
        """ Perform a single iteration of our capture -- essentially services the FaceDancer IRQs. """

        # FIXME: call a run_once on the FaceDancer scheduler; don't touch its internals

        for task in self.proxy.scheduler.tasks:
            task()
