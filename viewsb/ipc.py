"""
Support methods for communicating between ViewSB processes.
Used for comms between the frontend, backend, and analyzer threads.


This file is part of ViewSB
"""

import multiprocessing
import time
import threading
import traceback


def handle_exceptions(exception, traceback):
    """
    Callback that gets called when a exception is raised in a IPC process.
    Replace with your own stub to customize behavior, for eg. in a CLI application.
    """
    raise exception


class Process(multiprocessing.Process):
    """ Process class that forwards exceptions to the parent """

    def __init__(self, exception_handler, *args, **kwargs):
        multiprocessing.Process.__init__(self, daemon=True, *args, **kwargs)
        self._parent_conn, self._child_conn = multiprocessing.Pipe()
        self.exception_handler = exception_handler

    def run(self):
        try:
            multiprocessing.Process.run(self)
        except Exception as e:
            self.exception_handler(e, traceback.format_exc())

    @property
    def exit(self):
        if self._parent_conn.poll():
            self._exit = self._parent_conn.recv()
        return self._exception


class ProcessManager:
    """
    Base class for objects used to spawn and control remote processes.
    Subclasses are used by the analyzer thread to spawn Frontend and Backend processes.
    """

    _processes = []
    _scan_exit_thread_active = threading.Event()


    def __init__(self, remote_class, **remote_arguments):

        # Create our output queue and our termination-signaling event.
        self.data_queue        = multiprocessing.Queue()
        self.termination_event = multiprocessing.Event()

        # And put together our arguments.
        self.remote_arguments  = \
             [remote_class, remote_arguments, self.data_queue, self.termination_event]


    @staticmethod
    def _scan_bad_exits(processes):
        '''
        Scan the active process list and check if any of the processes exited with
        a bad (non-zero) code, if so, we terminate all other processes and exit
        ourselves with the same code.
        '''
        leave = False
        while not leave:
            for process in processes.copy():
                if process.exitcode:
                    leave = True
            time.sleep(0.2)

        for process in processes:
            if process.is_alive():
                process.terminate()
        exit(process.exitcode)


    def is_alive(self):
        """ Returns true iff the remote process is still running. """
        return self.remote_process.is_alive()


    def _get_process_name(self):
        """ Generates a default name for the given process. """
        return "{} process".format(self.remote_arguments[0].__name__)


    def start(self, *, vital=True):
        """
        Start the remote process, and allow it to begin processing.
        If the vital argument is set, we will exit if the process also exits.
        """

        # Ensure our termination event isn't set.
        self.termination_event.clear()

        # Generate a name for our capture process.
        name = self._get_process_name()

        # Create and start our background process.
        self.remote_process = \
            Process(exception_handler=handle_exceptions, target=self._subordinate_process_entry, args=self.remote_arguments, name=name)
        self.remote_process.start()

        if vital:
            self._processes.append(self.remote_process)
            if not self._scan_exit_thread_active.is_set():
                self._scan_exit_thread_active.set()
                self._scan_exit_thread = threading.Thread(
                    target=self._scan_bad_exits,
                    args=(self._processes,)
                )
                self._scan_exit_thread.start()


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

        if self.remote_process in self._processes:
            self._processes.remove(self.remote_process)


    @staticmethod
    def _subordinate_process_entry(remote_class, arguments, data_queue, termination_event):
        """
        Helper function for running a remote with a UI 'thread'. This method should usually be called in a subordinate
        process managed by multiprocessing. You probably want the public API of ViewSBFrontendProcess/ViewSBBackendProcess.
        """

        # Create a new instance of the task class.
        task = remote_class(**arguments)

        # Pass the new 'task' our IPC mechanisms, and then standard input.
        task.set_up_ipc(data_queue, termination_event)

        # Finally, run our 'task' until it terminates.
        try:
            task.run()
        except KeyboardInterrupt:
            pass
