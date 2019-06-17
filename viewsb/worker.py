"""
ViewSB Worker -- the primary logic for receiving USB data from a Backend (e.g. protocol analyzer hardware), running 
Decoders, and outputting data to a Frontend (e.g. our main GUI).
"""

from multiprocessing import Queue

class ViewSBWorker:
    """
    Primary processing "orchestrator" for ViewSB. Handles the actual logic of capturing data from the various backends,
    processing it, and then submitting it to the frontend for cataloging / display.
    """


    def __init__(self, backend, frontend, decoders=None):
        """ Creates a new ViewSB worker object, which is ready to run.

        Args:
            backend -- A 2-tuple, containing the type of backend that should be created and a tuple of arguments to that backend.
            frontend -- The single frontend that should receive the decoded data. 
            decoders -- A list of decoders to be applied. If not provided, all known decoders will be attempted; ViewSB
                decoders are intended to produce sane results with all filters enabled, so this is likely what you want.
        """

        # Generate the Queues we use for communication of packets from the backend, and to the frontend.
        self.backend_queue  = Queue()
        self.frontend_queue = Queue()
