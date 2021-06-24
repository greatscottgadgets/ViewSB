"""
Support methods for communicating between ViewSB processes.
Used for comms between the frontend, backend, and analyzer threads.


This file is part of ViewSB
"""

import multiprocessing
import traceback


class Process(multiprocessing.Process):
    """ Process class that forwards exceptions to the parent """

    def __init__(self, exception_conn, *args, **kwargs):
        multiprocessing.Process.__init__(self, daemon=True, *args, **kwargs)
        self._exception_conn = exception_conn

    def run(self):
        try:
            multiprocessing.Process.run(self)
        except Exception as e:
            self._exception_conn.send((e, traceback.format_exc()))


class ProcessManager:
    """
    Base class for objects used to spawn and control remote processes.
    Subclasses are used by the analyzer thread to spawn Frontend and Backend processes.
    """

    def __init__(
        self,
        remote_class,
        backend_setup_queue,
        backend_ready,
        in_except_conn,
        out_except_conn,
        **remote_arguments,
    ):

        # Create our output queue and our termination-signaling event.
        self.data_queue          = multiprocessing.Queue()
        self.backend_setup_queue = backend_setup_queue
        self.backend_ready       = backend_ready
        self.termination_event   = multiprocessing.Event()
        self._in_except_conn     = in_except_conn

        # And put together our arguments.
        self.remote_arguments = [
            remote_class,
            remote_arguments,
            self.data_queue,
            self.backend_setup_queue,
            self.backend_ready,
            self.termination_event,
            out_except_conn,
        ]


    def is_alive(self):
        """ Returns true iff the remote process is still running. """
        return self.remote_process.is_alive()


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
        self.remote_process = Process(
            self._in_except_conn,
            target=self._subordinate_process_entry,
            args=self.remote_arguments,
            name=name
        )
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


    @staticmethod
    def _subordinate_process_entry(
        remote_class,
        arguments,
        data_queue,
        backend_setup_queue,
        backend_ready,
        termination_event,
        exception_conn,
    ):
        """
        Helper function for running a remote with a UI 'thread'. This method should usually be called in a subordinate
        process managed by multiprocessing. You probably want the public API of ViewSBFrontendProcess/ViewSBBackendProcess.
        """

        # Create a new instance of the task class.
        task = remote_class(**arguments)

        # Pass the new 'task' our IPC mechanisms, and then standard input.
        task.set_up_ipc(data_queue, backend_setup_queue, backend_ready, termination_event, exception_conn)

        # Finally, run our 'task' until it terminates.
        try:
            task.run()
        except KeyboardInterrupt:
            pass
