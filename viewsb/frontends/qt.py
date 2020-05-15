"""
Qt Frontend for ViewSB


This file is part of ViewSB.
"""

import os
import multiprocessing

from datetime import datetime

from ..frontend import ViewSBFrontend
from ..packet import ViewSBPacket

try:
    from PySide2 import QtWidgets
    from PySide2.QtWidgets import QApplication, QWidget, QTreeWidget, QTreeWidgetItem
    from PySide2 import QtCore
    from PySide2.QtCore import QSize
    from PySide2.QtUiTools import QUiLoader


    class ViewSBQTreeWidget(QTreeWidget):
        """
        QDockWidgets don't let you set an initial size; instead, they work off the sizeHint() of their child.
        So, here's a QTreeWidget whose sizeHint() returns its dynamic property initialSize.
        """

        # Override
        def sizeHint(self):

            initial_size = self.property('initialSize')

            if initial_size is not None:
                return initial_size
            else:
                return QSize(0, 0)

except (ImportError, ModuleNotFoundError):
    pass


class QtFrontend(ViewSBFrontend):
    """ Qt Frontend that consumes packets for display. """

    UI_NAME = 'qt'
    UI_DESCRIPTION = 'unstable GUI in Qt'


    # So, Qt's tree widgets require that column 0 have the expand arrow, but you _can_ change
    # where column 0 is displayed.
    # We want the summary column to have the expand arrow, so we'll swap it with the timestamp column later.
    COLUMN_TIMESTAMP = 5
    COLUMN_DEVICE    = 1
    COLUMN_ENDPOINT  = 2
    COLUMN_DIRECTION = 3
    COLUMN_LENGTH    = 4
    COLUMN_SUMMARY   = 0
    COLUMN_STATUS    = 6
    COLUMN_DATA      = 7


    @staticmethod
    def reason_to_be_disabled():
        # If we weren't able to import PySide2, disable this frontend.
        if 'QWidget' not in globals():
            return "PySide2 (Qt library) not available"

        return None


    def _update_detail_fields(self, detail_fields):

        # Each table will have a root item in the details view.
        root_items = []

        for table in detail_fields:
            title = table[0]

            root = QTreeWidgetItem([title])
            children = []

            fields = table[1]

            # The usual case: a str:str dict.
            if isinstance(fields, dict):
                for key, value in fields.items():
                    children.append(QTreeWidgetItem([str(key), str(value)]))

            # Sometimes it'll just be a 1-column list.
            elif isinstance(fields, list):
                for item in fields:
                    children.append(QTreeWidgetItem([str(item)]))

            # Sometimes it'll just be a string, or a `bytes` instance.
            else:
                children.append(QTreeWidgetItem([str(fields)]))

            root.addChildren(children)

            # Add an empty "item" between each table
            root_items.extend([root, QTreeWidgetItem([])])


        self.window.usb_details_tree_widget.addTopLevelItems(root_items)

        self.window.usb_details_tree_widget.expandAll()

        self.window.usb_details_tree_widget.resizeColumnToContents(0)
        self.window.usb_details_tree_widget.resizeColumnToContents(1)


    def _get_item_for_packet(self, viewsb_packet):
        """ Creates a QTreeWidgetItem for a given ViewSBPacket.

        Args:
            viewsb_packet -- The ViewSBPacket to create the QTreeWidgetItem from.

        Returns a QTreeWidgetItem.
        """

        stringify_list = lambda l: [str(x) for x in l]

        def get_packet_string_array(viewsb_packet):
            """ Tiny helper to return and stringify the common fields used for the columns of tree items. """

            direction = viewsb_packet.direction.name if viewsb_packet.direction is not None else ''

            length = len(viewsb_packet.data) if viewsb_packet.data is not None else ''

            return stringify_list([
                viewsb_packet.summarize(),
                viewsb_packet.device_address,
                viewsb_packet.endpoint_number,
                direction,
                length,
                viewsb_packet.timestamp,
                viewsb_packet.summarize_status(),
                viewsb_packet.summarize_data()
                ]) + [viewsb_packet]


        item = QTreeWidgetItem(get_packet_string_array(viewsb_packet))

        # Give the item a reference to the original packet object.
        item.setData(0, QtCore.Qt.UserRole, viewsb_packet)

        return item


    def _recursively_walk_packet(self, viewsb_packet):
        """ Recursively walks packet subordinates, batching QTreeWidgetItem.addChildren as much as possible.

        Args:
            viewsb_packet -- The top-level packet (as far as the caller's context is concerned).
        """

        packet_item = self._get_item_for_packet(viewsb_packet)

        packet_children_list = []

        for sub_packet in viewsb_packet.subordinate_packets:

            # Create the item for this packet, and recursively fill its children.
            packet_children_list.append(self._recursively_walk_packet(sub_packet))


        packet_item.addChildren(packet_children_list)

        return packet_item


    def __init__(self):
        """ Sets up the Qt UI. """

        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts)

        self.app = QApplication([])
        self.ui_file = QtCore.QFile(os.path.dirname(os.path.realpath(__file__)) + '/qt.ui')

        self.loader = QUiLoader()
        self.loader.registerCustomWidget(ViewSBQTreeWidget)
        self.window = self.loader.load(self.ui_file)

        # Swap columns 0 and 5 to put the expand arrow on the summary column.
        self.window.usb_tree_widget.header().swapSections(0, 5)

        self.window.usb_tree_widget.setColumnWidth(self.COLUMN_TIMESTAMP, 120)
        self.window.usb_tree_widget.setColumnWidth(self.COLUMN_DEVICE,    32)
        self.window.usb_tree_widget.setColumnWidth(self.COLUMN_ENDPOINT,  24)
        self.window.usb_tree_widget.setColumnWidth(self.COLUMN_DIRECTION, 24)
        self.window.usb_tree_widget.setColumnWidth(self.COLUMN_LENGTH,    60)
        self.window.usb_tree_widget.setColumnWidth(self.COLUMN_SUMMARY,   500)

        self.window.update_timer = QtCore.QTimer()
        self.window.update_timer.timeout.connect(self.update)

        self.window.usb_tree_widget.currentItemChanged.connect(self.tree_current_item_changed)

        self.window.usb_tree_widget = self.window.usb_tree_widget
        self.window.usb_tree_widget.sortByColumn(0)


        self.window.showMaximized()


    def update(self):
        """ Called by the QTimer `update_timer`, collects packets waiting the queue and adds them to the tree view.

        Note: Since this is called via a QTimer signal, this method runs in the UI thread.
        """

        packet_list = []

        try:

            # Get as many packets as we can as quick as we can.
            while(True):

                packet = self.data_queue.get_nowait()
                packet_list.append(packet)

        # But the instant it's empty, don't wait for any more; just send them to be processed.
        except multiprocessing.queues.Empty:
            pass

        finally:
            self.add_packets(packet_list)


    def add_packets(self, viewsb_packets):
        """ Adds a list of top-level ViewSB packets to the tree.

        We're in the UI thread; every bit of overhead counts, so let's batch as much as possible.
        """

        top_level_items_list = []

        for viewsb_packet in viewsb_packets:

            # Create the item for this packet, and recursively fill its children.
            top_level_items_list.append(self._recursively_walk_packet(viewsb_packet))


        self.window.usb_tree_widget.addTopLevelItems(top_level_items_list)


    def tree_current_item_changed(self, current_item, previous_item):
        """ Use the side panel to show a detailed view of the current item. """

        # Clear the details widget.
        self.window.usb_details_tree_widget.clear()

        current_packet = current_item.data(0, QtCore.Qt.UserRole)

        # A list of 2-tuples: first element is a table title, and the second is usually a string:string dict
        detail_fields = current_packet.get_detail_fields()

        if detail_fields:
            self._update_detail_fields(detail_fields)


    def run(self):
        """ Overrides `ViewSBFrontend.run()` """

        # TODO: is there a better value than 100 ms? Should it be configurable by the Analyzer?
        self.window.update_timer.start(100)
        self.app.exec_()
        self.stop()

    def stop(self):
        self.app.closeAllWindows()
        self.termination_event.set()

