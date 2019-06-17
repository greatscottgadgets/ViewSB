"""
ViewSB backend class defintions -- defines the abstract base for things that capture USB data.
"""

import multiprocessing

class ViewSBBackend:
    """ Generic parent class for sources that capture USB data. """


    def __init__(self):
        """
        Function that initializes the relevant backend. In most cases, this objects won't be instantiated
        directly -- but instead instantiated by the `run_asynchronously` / 'run_backend_asynchronously` helpers.
        """
        pass


    def set_up_ipc(self, output_queue, termination_event):
        """
        Function that accepts the synchronization objects we'll use for output. Must be called prior to
        calling run().

        Args:
            output_queue -- The Queue object that will be fed any USB data generated.
            termination_event -- A synchronization event that is set when a capture is terminated.
        """

        # Store our IPC primitives, ready for future use.
        self.output_queue = output_queue
        self.termination_event = termination_event


    def run_capture(self):
        """
        Runs a single iteration of our backend capture.
        """
        pass


    def run(self):
        """ Runs the given backend until the provided termination event is set. """

        # Capture infinitely until our termination signal is set.
        while not self.termination_event.is_set():
            self.run_capture()








