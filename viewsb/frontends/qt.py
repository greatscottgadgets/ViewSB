"""
Qt Frontend for ViewSB


This file is part of ViewSB.
"""

import os
import math
import signal
import string
import multiprocessing

from ..frontend import ViewSBFrontend


try:
    from PySide6 import QtCore, QtWidgets
    from PySide6.QtWidgets import QApplication, QMainWindow
    from PySide6.QtWidgets import QTreeWidget, QTreeWidgetItem, QTableView, QAbstractItemView
    from PySide6.QtCore import Qt, QSize, QPoint, QItemSelection, QItemSelectionRange
    from PySide6.QtGui import QColor, QFont, QStandardItemModel, QStandardItem
    from PySide6.QtUiTools import QUiLoader

    class ViewSBQTreeWidget(QTreeWidget):
        """
        QDockWidgets don't let you set an initial size; instead, they work off the sizeHint() of their child.
        So, here's a QTreeWidget whose sizeHint() returns its dynamic property initialSize.
        """

        def sizeHint(self):
            """ Overrides QAbstractScrollArea.sizeHint(). """

            initial_size = self.property('initialSize')

            if initial_size is not None:
                return initial_size
            else:
                return QSize(0, 0)


    class ViewSBHexView(QTableView):
        """ Modified QTableView suitable for a hexview.

        This auto-switches between 8 bytes per row and 16 bytes per row based on what can fit in the widget's
        size, and auto-highlights the ASCII or hex item corresponding to the hex or ASCII item (respectively)
        the user selected.
        """


        def _to_corresponding_column(self, column):
            """ Returns the ASCII or hex column for the corresponding hex or ASCII column respectively. """

            bytes_per_row = self.model().columnCount() // 2

            if column < bytes_per_row:
                return column + bytes_per_row + 1
            else:
                return column - (bytes_per_row + 1)


        def _set_bytes_per_row(self, bytes_per_row):
            """ Sets up column count and column widths for the selected bytes-per-row (either 8 or 16). """

            assert bytes_per_row in (8, 16)

            # Hex columns, ASCII columns, and one separator column.
            column_count = bytes_per_row * 2 + 1
            self.model().setColumnCount(column_count)

            # Set column width for the hex columns, which each contain two characters.
            for column in range(bytes_per_row):
                self.setColumnWidth(column, self.hex_width)

            # Set the column width for the separator column.
            self.setColumnWidth(bytes_per_row, self.ascii_width * 2)

            # Set the column width for the ASCII columns, which each contain one character.
            for column in range(bytes_per_row + 1, column_count):
                self.setColumnWidth(column, self.ascii_width)


        def __init__(self, *args, **kwargs):

            super().__init__(*args, **kwargs)

            font = QFont('monospace', 8)
            font.setStyleHint(QFont.Monospace)
            self.setFont(font)
            self.setShowGrid(False)
            self.horizontalHeader().hide()
            self.verticalHeader().setSectionResizeMode(QtWidgets.QHeaderView.Fixed)
            self.verticalHeader().setHighlightSections(False)
            self.horizontalHeader().setHighlightSections(False)
            self.verticalHeader().setSectionsClickable(False)

            # Don't let the user edit the table cells.
            self.setEditTriggers(self.NoEditTriggers)

            self.setSelectionBehavior(QAbstractItemView.SelectItems)
            self.setSelectionMode(QAbstractItemView.ContiguousSelection)

            self.setModel(QStandardItemModel(1, 33))

            # This will store the raw data that is displayed in the hex view.
            self.hex_data = None

            # Determine how wide ASCII columns should be.
            self.ascii_width = self.fontMetrics().horizontalAdvance('m')

            # HACK: Get how much space a hex item needs by asking temporarily creating one, and then asking Qt,
            # because self.fontMetrics().width('mm') isn't enough, apparently, unlike above.
            self.model().setItem(0, 0, QStandardItem('mm'))
            self.resizeColumnToContents(0)
            self.hex_width = self.visualRect(self.model().createIndex(0, 0)).width()

            # Default to 16 hex columns, with 16 ASCII columns, and one separator column, for a total of 33.
            self._set_bytes_per_row(16)

            # HACK: Get how much space is needed for 16 bytes per row by
            # getting the left and right bound of the left-most and right-most items, respectively.
            start = self.visualRect(self.model().createIndex(0, 0)).left()
            end = self.visualRect(self.model().createIndex(0, 32)).right()
            self.full_width = end - start

            # Record the default background color for items, since apparently that's platform dependent.
            # Note: Normally we can only get the default background color if there's actually an item there,
            # but we made one earlier to determine the value for self.hex_width, so we don't need to do it again.
            self.default_background_color = self.model().item(0, 0).background()

            self.model().setRowCount(0)

            self.selectionModel().selectionChanged.connect(self._selection_changed)


        def setSelection(self, rect, flags):
            """ Overrides QTableView.setSelection().

            Qt Tables force multi-cell selections to be grid like, but we want this to act like a
            text box for selection purposes. That is to say that we want selections to wrap around.
            Since Qt doesn't have any setting that lets us do that, we have to subclass QTableView
            and reimplement setSelection.
            """

            def is_index_enabled(index):
                """ Reimplementation of the Qt private inline function of the same name."""
                return self.model().flags(index) & Qt.ItemIsEnabled


            #
            # Partial reimplementation of the original function.
            #

            tl = self.indexAt(QPoint(max(rect.left(), rect.right()) if self.isRightToLeft()
                else min(rect.left(), rect.right()), min(rect.top(), rect.bottom())))
            br = self.indexAt(QPoint(min(rect.left(), rect.right()) if self.isRightToLeft()
                else max(rect.left(), rect.right()), max(rect.top(), rect.bottom())))

            if (not self.selectionModel) or (not tl.isValid()) or (not br.isValid()) or \
                    (not is_index_enabled(tl)) or (not is_index_enabled(br)):
                return


            #
            # My code follows.
            #

            bytes_per_row = self.model().columnCount() // 2

            # Don't let the user touch or cross the separator.
            if tl.column() <= bytes_per_row <= br.column():
                return

            # Don't let the user select empty items.
            # Note: There's a reason we're using item() instead of itemFromIndex(), which is that
            # itemFromIndex() will lazily create an item at that index if there isn't one,
            # and we explicitly want to check if there is an item or not.
            if self.model().item(tl.row(), tl.column()) is None or \
                    self.model().item(br.row(), br.column()) is None:
                return


            selection = QItemSelection()

            selection_range = QItemSelectionRange(tl, br)
            if not selection_range.isEmpty():

                # Add this range, and then my custom range.
                selection.append(selection_range)

                # If we have a multi-line selection.
                if tl.row() < br.row():

                    # If the selection is on the hex side...
                    if br.column() < bytes_per_row:

                        # ...each line will be limited to first and last hex item of that row.
                        left_min = 0
                        right_max = bytes_per_row - 1

                    # If the selection is on the ASCII side...
                    else:

                        # ...each line will be limited to the first and last ASCII item of that row.
                        left_min = bytes_per_row + 1
                        right_max = bytes_per_row * 2

                    # Select the rest of each row except the bottom row.
                    for row in range(tl.row(), br.row()):

                        left_index = self.model().createIndex(row, tl.column())
                        right_index = self.model().createIndex(row, right_max)
                        selection.append(QItemSelectionRange(left_index, right_index))


                    # Select the beginning for each row except the top row.
                    for row in range(tl.row() + 1, br.row() + 1):

                        left_index = self.model().createIndex(row, left_min)
                        right_index = self.model().createIndex(row, br.column())
                        selection.append(QItemSelectionRange(left_index, right_index))


            self.selectionModel().select(selection, flags)


        def resizeEvent(self, event):
            """ Overrides QAbstractItemView.resizeEvent().

            This swaps the hexview between full mode and half mode based on what will fit.
            Full mode shows 16 hex items and 16 ASCII items per row.
            Half mode shows 8 hex items and 8 ASCII items per row.
            """

            super().resizeEvent(event)


            # If there's nothing in the hexview right now, we don't care.
            if self.model().rowCount() == 0:
                return


            # If we have enough room for full mode...
            if event.size().width() > self.full_width:

                # and we're not already in full mode...
                if self.model().columnCount() != 33:

                    # change to full mode...
                    self._set_bytes_per_row(16)

                    # and re-fill out the table.
                    self.populate(self.hex_data)

            # If we _don't_ have enough room for full mode...
            else:

                # and we're not already in half mode...
                if self.model().columnCount() != 17:

                    # change to half mode...
                    self._set_bytes_per_row(8)

                    # and re-fill out the table.
                    self.populate(self.hex_data)


        def _selection_changed(self, _selected, deselected):
            """
            Handler for the QTableView.selectionChanged() signal that highlights the ASCII or hex items that
            correspond to the hex or ASCII items the user selected, respectively.
            """

            # First, un-highlight the items that correspond to the ones that were deselected.
            for index in deselected.indexes():

                # Note: We're not using itemFromIndex() because it behaves slightly differently, and
                # under this setup it sometimes returns None.
                deselected_item = self.model().item(index.row(), index.column())

                other_item = self.model().item(deselected_item.row(),
                    self._to_corresponding_column(deselected_item.column()))

                # This can happen if e.g. the corresponding column was removed entirely
                # by switching to half mode.
                if other_item is not None:
                    other_item.setBackground(self.default_background_color)


            # Now, highlight the items that correspond to the ones that are currently selected.
            currently_selected_indexes = self.selectionModel().selectedIndexes()

            for index in currently_selected_indexes:

                # Highlight the corresponding other item.
                other_item = self.model().item(index.row(),
                    self._to_corresponding_column(index.column()))
                other_item.setBackground(QColor('#DDDD55'))


        def populate(self, raw_data):
            """ Populate the hex and ASCII items.

            Args:
                raw_data -- bytes object containing the raw binary data to be displayed.
            """

            def row_column_enumerate(iterable):
                """ Turns the index into row-column coordinates suitable for a hexview."""
                for index, value in enumerate(iterable):
                    yield divmod(index, self.model().columnCount() // 2), value


            self.hex_data = raw_data

            model = self.model()

            # Reset.
            # Note: We're not using clear() as that would also clear e.g. column settings.
            model.setRowCount(0)

            # Calculate how many rows we need.
            bytes_per_row = model.columnCount() // 2
            data_len = len(raw_data)
            needed_rows = math.ceil(data_len / bytes_per_row)

            model.setRowCount(needed_rows)

            address_labels = ['{:04X}'.format(i) for i in range(0, data_len, bytes_per_row)]
            model.setVerticalHeaderLabels(address_labels)

            for (row, col), byte in row_column_enumerate(raw_data):

                hex_item = QStandardItem('{:02X}'.format(byte))
                char = chr(byte)
                if char in string.printable:
                    ascii_item = QStandardItem(char)
                else:
                    ascii_item = QStandardItem('·')

                model.setItem(row, col, hex_item)
                model.setItem(row, self._to_corresponding_column(col), ascii_item)


except (ImportError, ModuleNotFoundError):
    pass


class QtFrontend(ViewSBFrontend):
    """ Qt Frontend that consumes packets for display. """

    UI_NAME = 'qt'
    UI_DESCRIPTION = 'unstable GUI in Qt'


    # So, Qt's tree widgets require that column 0 have the expand arrow, but you _can_ change
    # where column 0 is displayed.
    # We want the summary column to have the expand arrow, so we'll swap it
    # with the timestamp column in __init__().
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
        try:
            import PySide6
        except ImportError:
            return "PySide6 (Qt library) not available."

        return None


    @staticmethod
    def _stringify_list(lst):
        """
        Tiny helper than runs the str constructor on every item in a list, but specifically handles two cases:
        1) the object in question is None, which we instead want to display as an empty string,
        2) the resulting string contains a null character, which Qt doesn't like, so we'll
        represent it to the user as, literally, \0.
        """
        return [str(x).replace('\0', r'\0') if x is not None else '' for x in lst]


    def _create_item_for_packet(self, viewsb_packet):
        """ Creates a QTreeWidgetItem for a given ViewSBPacket.

        Args:
            viewsb_packet -- The ViewSBPacket to create the QTreeWidgetItem from.

        Returns a QTreeWidgetItem.
        """

        def get_packet_string_array(viewsb_packet):
            """ Tiny helper to return and stringify the common fields used for the columns of tree items. """

            direction = viewsb_packet.direction.name if viewsb_packet.direction is not None else ''

            length = len(viewsb_packet.data) if viewsb_packet.data is not None else ''

            return self._stringify_list([
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

        packet_item = self._create_item_for_packet(viewsb_packet)

        packet_children_list = []

        for sub_packet in viewsb_packet.subordinate_packets:

            # Create the item for this packet, and recursively fill its children.
            packet_children_list.append(self._recursively_walk_packet(sub_packet))


        packet_item.addChildren(packet_children_list)

        return packet_item


    def __init__(self):
        """ Sets up the Qt UI. """

        super().__init__()
        QtCore.QCoreApplication.setAttribute(QtCore.Qt.AA_ShareOpenGLContexts)

        signal.signal(signal.SIGINT, signal.SIG_DFL)  # fix SIGINT handling - cleanly exit on ctrl+c

        self.app = QApplication.instance() or QApplication([])

        try:
            import qt_material

            qt_material.apply_stylesheet(self.app, 'light_blue.xml')
        except ImportError:
            pass

        self.ui_file = QtCore.QFile(os.path.dirname(os.path.realpath(__file__)) + '/qt.ui')
        self.loader = QUiLoader()
        self.loader.registerCustomWidget(ViewSBQTreeWidget)
        self.loader.registerCustomWidget(ViewSBHexView)
        self.window = self.loader.load(self.ui_file) # type: QMainWindow

        # Swap columns 0 and 5 to put the expand arrow on the summary column.
        self.window.usb_tree_widget.header().swapSections(0, 5)

        self.window.usb_tree_widget.header().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)

        self.window.update_timer = QtCore.QTimer()
        self.window.update_timer.timeout.connect(self._update)

        self.window.usb_tree_widget.currentItemChanged.connect(self._tree_current_item_changed)

        self.window.usb_tree_widget = self.window.usb_tree_widget
        self.window.usb_tree_widget.sortByColumn(0, Qt.SortOrder.AscendingOrder)


    def ready(self):
        """ Called when the backend is ready to stream. """
        self.window.showMaximized()


    def _update(self):
        """ Called by the QTimer `update_timer`; collects packets the queue and adds them to the tree view.

        We use this instead of calling `handle_communications` and defining `handle_incoming_packet`,
        because adding items one at a time as we receive them is slower than batching them.

        Note: Since this is called via a QTimer signal, this method runs in the UI thread.
        """

        # Handle exceptions
        if self._exception_conn.poll():
            self.handle_exception(*self._exception_conn.recv())
            # TODO: overide handle_exception to show a Qt dialog message

        # If the process manager told us to stop (which might happen if e.g. the backend exits),
        # then stop and exit.
        if self.termination_event.is_set():
            self.app.closeAllWindows()

        packet_list = []

        try:

            # Get as many packets as we can as quick as we can.
            while True:

                packet = self.data_queue.get_nowait()
                packet_list.append(packet)

        # But the instant it's empty, don't wait for any more; just send them to be processed.
        except multiprocessing.queues.Empty:
            pass

        finally:
            self.add_packets(packet_list)


    def _tree_current_item_changed(self, current_item, _previous_item):
        """
        Handler for the QTreeWidget.currentItemChanged() signal that populates the side panels with
        detail fields and a hex representation of the current packet.
        """

        # Clear the details widget.
        self.window.usb_details_tree_widget.clear()

        current_packet = current_item.data(0, QtCore.Qt.UserRole)

        # A list of 2-tuples: first element is a table title, and the second is usually a string:string dict.
        detail_fields = current_packet.get_detail_fields()

        if detail_fields:
            self.update_detail_fields(detail_fields)

        self.window.usb_hex_view.populate(current_packet.get_raw_data())


    def update_detail_fields(self, detail_fields):
        """ Populates the detail view with the relevant fields for the selected packet. """

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
                    children.append(QTreeWidgetItem(self._stringify_list([key, value])))

            # Sometimes it'll just be a 1-column list.
            elif isinstance(fields, list):
                for item in fields:
                    children.append(QTreeWidgetItem(self._stringify_list([item])))

            # Sometimes it'll just be a string, or a `bytes` instance.
            else:
                children.append(QTreeWidgetItem(self._stringify_list([fields])))

            root.addChildren(children)

            # Add an empty "item" between each table.
            root_items.extend([root, QTreeWidgetItem([])])


        self.window.usb_details_tree_widget.addTopLevelItems(root_items)

        self.window.usb_details_tree_widget.expandAll()

        self.window.usb_details_tree_widget.resizeColumnToContents(0)
        self.window.usb_details_tree_widget.resizeColumnToContents(1)


    def add_packets(self, viewsb_packets):
        """ Adds a list of top-level ViewSB packets to the tree.

        We're in the UI thread; every bit of overhead counts, so let's batch as much as possible.
        """

        top_level_items_list = []

        for viewsb_packet in viewsb_packets:

            # Create the item for this packet, and recursively fill its children.
            top_level_items_list.append(self._recursively_walk_packet(viewsb_packet))


        self.window.usb_tree_widget.addTopLevelItems(top_level_items_list)


    def run(self):
        """ Overrides ViewSBFrontend.run(). """

        self.wait_for_backend_ready()

        # TODO: is there a better value than 100 ms? Should it be configurable by the Analyzer?
        self.window.update_timer.start(100)
        self.app.exec_()
        self.stop()

    def stop(self):
        self.app.closeAllWindows()
        self.termination_event.set()
