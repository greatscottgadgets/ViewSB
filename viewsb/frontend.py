"""
ViewSB frontend class defintions -- defines the abstract base for things that display USB data
"""

import io
import sys
import queue

from .ipc import ProcessManager


class ViewSBFrontendProcess(ProcessManager):
    """ Class that controls and communicates with a ViewSB UI running in another process. """
    pass



class ViewSBFrontend:
    """ Generic parent class for sources that display USB data. """

    PACKET_READ_TIMEOUT = 0.01

    def __init__(self):
        """
        Function that initializes the relevant frontend. In most cases, this objects won't be instantiated
        directly -- but instead instantiated by the `run_asynchronously` / 'run_frontend_asynchronously` helpers.
        """
        pass


    def set_up_ipc(self, data_queue, termination_event, stdin=None):
        """
        Function that accepts the synchronization objects we'll use for input. Must be called prior to
        calling run().

        Args:
            data_queue -- The Queue object that will feed up analyzed packets for display.
            termination_event -- A synchronization event that is set when a capture is terminated.
        """

        # Store our IPC primitives, ready for future use.
        self.data_queue        = data_queue
        self.termination_event = termination_event

        # Retrieve our use of the standard input from the parent thread.
        if stdin:
            self.stdin = sys.stdin = stdin



    def read_packet(self, blocking=True, timeout=None):
        """ Reads a packet from the analyzer process.

        Args:
            blocking -- If set, the read will block until a packet is available.
            timeout -- The longest time to wait on a blocking read, in floating-point seconds.
        """
        return self.data_queue.get(blocking, timeout=timeout)


    def handle_events(self):
        pass


    def handle_incoming_packet(self, packet):
        pass


    def fetch_packet_from_analyzer(self):
        """
        Fetch any packets the analyzer has to offer. Blocks for a short period if no packets are available,
        to minimize CPU busy-waiting.
        """

        try:
            # Read a packet from the backend, and add it to our analysis queue.
            return self.read_packet(timeout=self.PACKET_READ_TIMEOUT, blocking=False)

        except queue.Empty:
            # If no packets were available, return without error; we'll wait again next time.
            return None


    def handle_communications(self):
        """ 
        Function that handles communications with our analyzer process.
        Should be called repeatedly during periods when the UI thread is not busy;
        if you override run(). it's your responsibility to call this function.
        """

        packet = True

        while packet:

            # Try to fetch a packet from the analyzer.
            packet = self.fetch_packet_from_analyzer()
            
            # If we got one, handle using it in our UI.
            if not packet:
                break

            self.handle_incoming_packet(packet)


    def run(self):
        """ Runs the given frontend until either side requests termination. """

        # Capture infinitely until our termination signal is set.
        while not self.termination_event.is_set():
            self.handle_communications()

        # Allow the subclass to handle any cleanup it needs to do.
        self.handle_termination()


    def handle_termination(self):
        """ Called once the capture is terminated; gives the frontend the ability to clean up. """
        pass

