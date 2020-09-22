"""
GTK Frontend for ViewSB


This file is part of ViewSB
"""

import os.path
import threading

try:
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk, GObject

    class GtkFrontendApp(Gtk.ApplicationWindow):
        pass
except ImportError:
    pass

from ...frontend import ViewSBFrontend


class GtkFrontend(ViewSBFrontend):
    UI_NAME = 'gtk'
    UI_DESCRIPTION = 'unstable GUI in GTK'

    _DATA = {
        'Timestamp': GObject.TYPE_ULONG,
        'Device': GObject.TYPE_UINT,
        'Endpoint': GObject.TYPE_UINT,
        'Direction': str,
        'Length': GObject.TYPE_UINT,
        'Summary': str,
        'Status': str,
        'Data': str,
        '_id': GObject.TYPE_ULONG,
    }

    _DATA_DETAIL = {
        'Property': str,
        'Value': str,
    }

    class _GtkHandler:
        def __init__(self, parent):
            self.parent = parent

        def on_application_exit(self, *args):
            Gtk.main_quit()
            if self.parent._app_run_event:
                self.parent._app_run_event.clear()

        def on_packet_cursor_changed(self, treeview):
            model, treeiter = treeview.get_selection().get_selected()
            if treeiter is not None:
                packet = self.parent._packets[model[treeiter][8]]

                # fill hexview
                self.parent._label_hexview.set_text(' '.join(f'{b:02x}' for b in packet.data))

                # fill packet details
                if detail_fields := packet.get_detail_fields():
                    self.parent.update_detail_fields(detail_fields)

        def on_scrolledwindowdata_size_allocate(self, widget, *args):
            # autoscroll
            # TODO: skip when row is selected
            adjustment = widget.get_vadjustment()
            adjustment.set_value(adjustment.get_upper() - adjustment.get_page_size())

    @staticmethod
    def reason_to_be_disabled():
        try:
            import gi
        except ImportError:
            return 'PyGObject (gi) not available'

        try:
            gi.require_version("Gtk", "3.0")
        except ImportError:
            return 'GTK 3.0 not available'

        return None

    def __init__(self):
        self._app_run_event = threading.Event()
        self._packets = []

        self._ui = {}
        for ui in ('MainWindow',):
            self._ui[ui] = os.path.join(os.path.dirname(__file__), f'{ui}.glade')

        self._builder = Gtk.Builder()
        self._builder.add_from_file(self._ui['MainWindow'])

        self._builder.connect_signals(self._GtkHandler(self))

        self._scrolledwindowData = self._builder.get_object('scrolledwindowData')

        self._treeview_data = self._builder.get_object('treeviewData')
        self._liststore_data = Gtk.ListStore(*self._DATA.values())
        self._treeview_data.set_model(self._liststore_data)
        self._init_treeview_data_columns()

        self._panned_data_details = self._builder.get_object('pannedDataDetails')
        self._label_hexview = self._builder.get_object('labelHexview')

        self._treeview_data_detail = self._builder.get_object('treeviewDataDetail')
        self._treestore_data_detail = Gtk.TreeStore(*self._DATA_DETAIL.values())
        self._treeview_data_detail.set_model(self._treestore_data_detail)
        self._init_treeview_data_detail_columns()

        self._window = self._builder.get_object('window')
        self._window.show_all()

        self._gtk_thread = threading.Thread(target=Gtk.main)

    def _init_treeview_data_columns(self):
        for i, column in enumerate(self._DATA.keys()):
            if column.startswith('_'):
                continue
            cell = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(column, cell, text=i)
            self._treeview_data.append_column(col)

    def _init_treeview_data_detail_columns(self):
        for i, column in enumerate(self._DATA_DETAIL.keys()):
            cell = Gtk.CellRendererText()
            col = Gtk.TreeViewColumn(column, cell, text=i)
            self._treeview_data_detail.append_column(col)

    def handle_incoming_packet(self, packet):
        self._packets.append(packet)
        self._liststore_data.append((
            packet.timestamp,
            packet.device_address,
            packet.endpoint_number,
            packet.direction.name,
            len(packet.data),
            packet.summarize(),
            packet.summarize_status(),
            packet.summarize_data() or '',
            len(self._packets) - 1,
        ))

    def run(self):
        self._gtk_thread.start()
        self._app_run_event.set()

        while self._app_run_event.is_set():
            self.handle_communications()

        self.handle_termination()

    def update_detail_fields(self, detail_fields):
        self._treestore_data_detail.clear()

        for table in detail_fields:
            title = table[0]
            fields = table[1]

            parent = self._treestore_data_detail.append(None, (title, ''))

            # the usual case: a str:str dict
            if isinstance(fields, dict):
                for key, value in fields.items():
                    self._treestore_data_detail.append(parent, (str(key), str(value)))

            # sometimes it'll just be a 1-column list
            elif isinstance(fields, list):
                for item in fields:
                    self._treestore_data_detail.append(parent, (str(item), ''))

            # sometimes it'll just be a string, or a `bytes` instance
            else:
                self._treestore_data_detail.append(parent, (str(fields), ''))

        self._treeview_data_detail.expand_all()
