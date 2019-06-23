"""
ViewSB Worker -- the primary logic for receiving USB data from a Backend (e.g. protocol analyzer hardware), running
Decoders, and outputting data to a Frontend (e.g. our main GUI).
"""

import queue

from .decoder import ViewSBDecoder
from .decoders import *

from .backend import ViewSBBackendProcess
from .frontend import ViewSBFrontendProcess



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

        # Create -- but don't start -- our frontend process.
        frontend_class, frontend_arguments = frontend
        self.frontend = ViewSBFrontendProcess(frontend_class, *frontend_arguments)



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

        # Pass the packet to the frontend.
        self.frontend.issue_packet(packet)



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
            packet = self.backend.read_packet(timeout=self.PACKET_READ_TIMEOUT)
            self.analysis_queue.put(packet)

        except queue.Empty:
            # If no packets were available, return without error; we'll wait again next time.
            pass


    def packets_may_arrive(self):
        """ Returns true iff the backend is alive enough to send us packets. """
        return True


    def run_analysis_iteration(self):
        """ 
        Runs a single iteration of our analysis process.
        This queries the backend for packets -once-, and then analyzes them.
        """
        self.process_analysis_queue()
        self.fetch_backend_packets()


    def should_halt(self):
        """ Returns true if the analyzer process should halt. """

        # If the frontend has died, we should terminate.
        if not self.frontend.is_alive():
            return True

        # TODO: check termination conditions?

        return False


    def run(self):
        """ Run this core analysis thread until the frontend requests we stop. Performs the USB analysis itself. """

        # Pass the frontend stdin; this allows console-interactive analyzer to work.
        # We implicitly give up stdin by calling this.
        self.frontend.pass_stdin()

        # Start our core bg/fg threads.
        self.backend.start()
        self.frontend.start()

        # Run our analysis main-loop until we should quit.
        while not self.should_halt():

            # TODO: handle event-packet exchange with the UI
            # this should be coming Soon (TM)

            # If we're in a state where packets may arrive, try to receive them.
            if self.packets_may_arrive():
                self.run_analysis_iteration()

            # Otherwise, block the process a bit to give the CPU some time off.
            else:
                time.sleep(self.PACKET_READ_TIMEOUT)


        # FIXME: signal to the frontend to stop (if it didn't signal us to stop?)
        self.backend.stop()
        self.frontend.stop()
