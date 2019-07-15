"""
Qt Frontend for ViewSB


This file is part of ViewSB
"""

import os
import multiprocessing

from datetime import datetime

try:
    import PySide2
    from PySide2 import QtWidgets
    from PySide2.QtWidgets import QApplication, QWidget
    from PySide2 import QtCore
    from PySide2.QtCore import Qt, QObject
    from PySide2.QtUiTools import QUiLoader
except (ImportError, ModuleNotFoundError):
    pass


from ..frontend import ViewSBFrontend
from ..packet import ViewSBPacket


def stringify_list(l: []) -> [str]:
    """ Tiny helper to cast every item in a list to a string, since Qt only likes displaying strings. """
    return [str(x) for x in l]


def get_packet_string_array(viewsb_packet):
    """ Tiny helper to return and stringify the common fields used for the columns of tree items. """
    return stringify_list([viewsb_packet.timestamp, viewsb_packet.summarize(), viewsb_packet.summarize_status(), viewsb_packet.summarize_data()] + [viewsb_packet])


def recursive_packet_walk(viewsb_packet, packet_children_list):
    """ Recursively walks packet subordinates, batching QTreeWidgetItem.addChildren as much as possible.

    Args:
        viewsb_packet        -- The top-level packet (as far as the caller's context is concerned).
        packed_children_list -- List to be filled with `viewsb_packet`'s children as `QTreeWidgetItem`s.
    """

    packet_item = QtWidgets.QTreeWidgetItem(get_packet_string_array(viewsb_packet))

    for sub_packet in viewsb_packet.subordinate_packets:

        sub_item = QtWidgets.QTreeWidgetItem(get_packet_string_array(sub_packet))
        sub_item.setData(0, QtCore.Qt.UserRole, sub_packet)

        # Recursively populate `sub_item`'s children.
        children = []
        recursive_packet_walk(sub_packet, children)

        # Add our subordinate (and it's entire hierarchy) as a child of our parent.
        packet_children_list.append(sub_item)



class QtFrontend(ViewSBFrontend):
    """ Qt Frontend that consumes packets for display. """

    UI_NAME = 'qt'
    UI_DESCRIPTION = 'proof-of-concept, unstable GUI in Qt'


    @staticmethod
    def reason_to_be_disabled():
        # If we weren't able to import pyside2, disable the library.
        if 'QWidget' not in globals():
            return "pyside2 (qt library) not available"

        return None


    def __init__(self):
        """ Sets up the Qt UI. """

        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts)

        self.app = QApplication([])
        self.ui_file = QtCore.QFile(os.path.dirname(os.path.realpath(__file__)) + '/qt.ui')

        self.loader = QUiLoader()
        self.window: QtWidgets.QMainWindow = self.loader.load(self.ui_file)

        # The default column size of 100 is too small for the summary column.
        self.window.usb_tree_widget.setColumnWidth(1, 400)

        self.window.update_timer = QtCore.QTimer()
        self.window.update_timer.timeout.connect(self.update)

        self.window.usb_tree_widget.currentItemChanged.connect(self.tree_current_item_changed)

        self.window.usb_tree_widget: QtWidgets.QTreeWidget = self.window.usb_tree_widget
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
            # In case the queue was empty in the first place and didn't have anything ready.
            if len(packet_list) > 0:

                self.add_packets(packet_list)


    def add_packets(self, viewsb_packets: []):
        """ Adds a list of top-level ViewSB packets to the tree.

        We're in the UI thread; every bit of overhead counts, so let's batch as much as possible.
        """

        for viewsb_packet in viewsb_packets:
            top_level_item = QtWidgets.QTreeWidgetItem(get_packet_string_array(viewsb_packet))
            top_level_item.setData(0, QtCore.Qt.UserRole, viewsb_packet)

            list_of_children = []
            recursive_packet_walk(viewsb_packet, list_of_children)

            top_level_item.addChildren(list_of_children)

            self.window.usb_tree_widget.addTopLevelItem(top_level_item)

    def tree_current_item_changed(self, current_item, previous_item):
        """ Use the side panel to show a detailed view of the current item. """

        # Clear the details widget.
        self.window.usb_details_tree_widget.clear()

        self.window.usb_details_tree_widget.setColumnCount(2)

        current_packet: ViewSBPacket = current_item.data(0, QtCore.Qt.UserRole)

        # A list of 2-tuples: first element is a table title, and the second is usually a string: string dict
        detail_fields = current_packet.get_detail_fields()

        # Each table will have a root item in the details view.
        root_items = []

        for table in detail_fields:
            title: str = table[0]

            root = QtWidgets.QTreeWidgetItem([title])
            children = []

            fields = table[1]

            # The usual case: a str: str dict.
            if type(fields) == type({}):
                for key, value in fields.items():
                    children.append(QtWidgets.QTreeWidgetItem(stringify_list([key, value])))

            # Sometimes a descriptor will just be a 1-column list.
            elif type(fields) == type([]):
                for item in fields:
                    children.append(QtWidgets.QTreeWidgetItem([str(item)]))

            # Sometimes it'll just be a string, or, if it's an unknown descriptor, a `bytes` instance.
            else:
                children.append(QtWidgets.QTreeWidgetItem([str(fields)]))

            root.addChildren(children)

            # Add an empty "item" between each table
            root_items += [root, QtWidgets.QTreeWidgetItem([])]


        self.window.usb_details_tree_widget.addTopLevelItems(root_items)

        self.window.usb_details_tree_widget.expandAll()

        self.window.usb_details_tree_widget.resizeColumnToContents(0)
        self.window.usb_details_tree_widget.resizeColumnToContents(1)

    def run(self):
        """ Overrides `ViewSBFrontend.run()` """

        # TODO: is there a better value than 100 ms? Should it be configurable by the Analyzer?
        self.window.update_timer.start(100)
        self.app.exec_()
        self.stop()

    def stop(self):
        self.app.closeAllWindows()
        self.termination_event.set()

