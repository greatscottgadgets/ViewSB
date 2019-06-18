#!/usr/bin/env python3
"""
Simple, temporary test harness for ViewSB.
"""

from viewsb import ViewSBAnalyzer
from viewsb.backends.usbproxy import USBProxyBackend


# Use the USBProxy backend to proxy a HackRF,
backend  = (USBProxyBackend, (0x1d50, 0x6089))
frontend = None # TODO

# Create our analyzer object.
analyzer = ViewSBAnalyzer(backend, frontend)

# Run the analyzer.
analyzer.run()


