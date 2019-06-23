#!/usr/bin/env python3
"""
Simple, temporary test harness for ViewSB.
"""

import sys

from viewsb import ViewSBAnalyzer

from viewsb.frontends.cli import CLIFrontend
from viewsb.frontends.tui import TUIFrontend
from viewsb.backends.usbmon import USBMonFileBackend


backend  = (USBMonFileBackend, (sys.argv[1], ) )


frontend = (TUIFrontend, ())
#frontend = (CLIFrontend, ())

# Create our analyzer object.
analyzer = ViewSBAnalyzer(backend, frontend)

# Run the analyzer.
analyzer.run()


