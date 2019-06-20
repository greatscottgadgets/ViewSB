#!/usr/bin/env python3
"""
Simple, temporary test harness for ViewSB.
"""

from openvizsla import OVCaptureUSBSpeed

from viewsb import ViewSBAnalyzer

from viewsb.packet import USBPacketID
from viewsb.backends.openvizsla import OpenVizslaBackend

# For current test sanity, suppress SOF packets.
def suppress_packet(packet):
    return packet.pid == USBPacketID.SOF


# Capture a high speed device using OV.
backend  = (OpenVizslaBackend, (OVCaptureUSBSpeed.HIGH, suppress_packet, ))
frontend = None # TODO

# Create our analyzer object.
analyzer = ViewSBAnalyzer(backend, frontend)

# Run the analyzer.
analyzer.run()


