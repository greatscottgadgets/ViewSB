"""
Support methods for communicating between ViewSB processes.
Used for comms between the frontend, backend, and analyzer threads.
"""

import os
import sys
import multiprocessing


class ProcessManager:
    """ 
    Base class for objects used to spawn and control remote processes.
    Subclasses are used by the analyzer thread to spawn Frontend and Backend processes.
    """

    def __init__(self, remote_class, *remote_arguments):

        # Create our output queue and our termination-signaling event.
        self.data_queue        = multiprocessing.Queue()
        self.termination_event = multiprocessing.Event()

        # And put together our arguments.
        self.remote_arguments  = \
             [remote_class, remote_arguments, self.data_queue, self.termination_event]


    def is_alive(self):
        """ Returns true iff the remote process is still running. """
        return self.remote_process.is_alive()


    def pass_stdin(self):
        """ Sets up pasing stdin to the relevant process; removing it from the calling one. """

        # Create a duplicate of stdin for the remote process that will continue
        # to exist. If we don't create this copy, python's multiprocessing will
        # close the new class's stdin after the fork/spawn.
        remote_stdin = self._capture_stdin()

        # Add this new stdin to the remote arguments.
        self.remote_arguments.append(remote_stdin)

        # Since we're handing stdin to the remote process; we shouldn't use
        # our local copy. Close it.
        sys.stdin.close()


    def _get_process_name(self):
        """ Generates a default name for the given process. """
        return "{} process".format(self.remote_arguments[0].__name__)


    def start(self):
        """ Start the remote process, and allow it to begin processing. """

        # Ensure our termination event isn't set.
        self.termination_event.clear()

        # Generate a name for our capture process.
        name = self._get_process_name()

        # Create and start our background process.
        self.remote_process = \
            multiprocessing.Process(target=self._subordinate_process_entry, args=self.remote_arguments, name=name)
        self.remote_process.start()


    def issue_packet(self, packet):
        """ Consumes packets from the analyzer, and sends them over to the remote process. """
        self.data_queue.put(packet)


    def read_packet(self, blocking=True, timeout=None):
        """ Reads a packet from the remote process.

        Args:
            blocking -- If set, the read will block until a packet is available.
            timeout -- The longest time to wait on a blocking read, in floating-point seconds.
        """
        return self.data_queue.get(blocking, timeout=timeout)


    def stop(self):
        """ 
        Request that the remote process stop. 
        """
        self.termination_event.set()
        self.remote_process.join()


    def _capture_stdin(self):
        """ 
        Currently, the multiprocessing module kills stdin on any newly-spawned processes; and doesn't
        allow us to configure which of the multiple processe retains a living stdin.

        To work around this, we'll break stdin away from python's control, and manually pass it to
        the subordinate processes.
        """

        # Create a duplicate handle onto the standard input.
        # This effectively increases the file's refcount, preventing python from disposing of it.
        fd_stdin = sys.stdin.fileno()
        return os.fdopen(os.dup(fd_stdin))


    @staticmethod
    def _subordinate_process_entry(remote_class, arguments, data_queue, termination_event, stdin=None):
        """
        Helper function for running a remote with a UI 'thread'. This method should usually be called in a subordinate
        process managed by multiprocessing. You probably want the public API of ViewSBFrontendProcess/ViewSBBackendProcess.
        """

        # Create a new instance of the task class.
        task = remote_class(*arguments)

        # Pass the new 'task' our IPC mechanisms, and then standard input.
        task.set_up_ipc(data_queue, termination_event, stdin)

        # Finally, run our 'task' until it terminates.
        task.run()
