"""
ViewSB Worker -- the primary logic for receiving USB data from a Backend (e.g. protocol analyzer hardware), running 
Decoders, and outputting data to a Frontend (e.g. our main GUI).
"""

import queue

from .decoder import ViewSBDecoder
from .decoders import *

from .backend import ViewSBBackendProcess


class ViewSBAnalyzer:
    """
    Primary processing "orchestrator" for ViewSB. Handles the actual logic of capturing data from the various backends,
    processing it, and then submitting it to the frontend for cataloging / display.
    """

    PACKET_READ_TIMEOUT = 0.1

    def __init__(self, backend, frontend, decoders=None):
        """ Creates a new ViewSB worker object, which is ready to run.

        Args:
            backend  -- A 2-tuple, containing the type of backend that should be created,
                        and a tuple of arguments to that backend.
            frontend -- A 2-tuple, containing the type of frontend that will receive analyzed data, 
                        and a tuple of arguments to that frontend.
            decoders -- A list of decoder classes to be applied. If not provided, all known decoders will be attempted;
                        ViewSB decoders are intended to produce sane results with all filters enabled, so this is likely 
                        what you want.
        """

        # If decoders weren't specified, use all decoders.
        if decoders is None:

            # FIXME: this should be ViewSBDecoder.__subclasses__
            decoders = ViewSBDecoder.all_decoders()

        # Instantiate each of our decoder classes.
        self.decoders = [decoder(self) for decoder in decoders]

        # Create our analysis queue.
        self.analysis_queue = queue.Queue()

        # Create -- but don't start -- our backend process.
        backend_class, backend_arguments = backend
        self.backend = ViewSBBackendProcess(backend_class, *backend_arguments)
        
        # TODO: Create -- but don't start -- our frontend process.


    def process_analysis_queue(self):
        """ Processes any packets in the analysis queue. """

        # Loop until the analysis queue is empty.
        while True:

            try:
                # Read a packet from the analysis queue.
                packet = self.analysis_queue.get_nowait()
            except queue.Empty:

                # If we're out of packets, return.
                return

            # Try to run the packet through all of our decoders.
            handled = False
            for decoder in self.decoders:

                # See if the given decoder wants to consume this packet...
                handled = decoder.handle_packet(packet)

                # ... and if it was, break out of it.
                if handled:
                    break

            # If the packet wasn't consumed by any our decoders,
            # we're done processing it. Emit it to the frontend.
            if not handled:
                self.emit_to_frontend(packet)


    def emit_to_frontend(self, packet):
        """ Emits a given packet to the frontend, for use. """

        # XXX: temporary, for debug only
        # just print; no fancy frontend
        print(repr(packet))


    def add_packet_to_analysis_queue(self, packet):
        """
        Adds the provided packet to the analysis queue.
        Intended for use by the decoder API; not recommended for general use.
        """
        self.analysis_queue.put(packet)


    def fetch_backend_packets(self):
        """
        Fetch any packets the backend has to offer. Blocks for a short period if no packets are available,
        to minimize CPU busy-waiting.
        """

        try:
            # Read a packet from the backend, and add it to our analysis queue.
            packet = self.backend.read_packet(timeout=self.process_analysis_queue)
            self.analysis_queue.put(packet)

        except queue.Empty:
            # If no packets were available, return without error; we'll wait again next time.
            pass


    def run(self):
        """ Run this core analysis thread until the frontend requests we stop. Performs the USB analysis itself. """

        self.backend.start()

        # FIXME: this should ask the FrontendProcess object whether it should halt.
        try:
            while True:
                self.process_analysis_queue()
                self.fetch_backend_packets()

        # For now, always break on a keyboard interrupt.
        except KeyboardInterrupt:
            pass

        # FIXME: signal to the frontend to stop (if it didn't signal us to stop?)
        self.backend.stop()
