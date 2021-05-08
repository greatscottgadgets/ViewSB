"""
Quick experiment with a TUI frontend


This file is part of ViewSB
"""

import urwid
import string
import collections

from usb_protocol.types import USBDirection

from ..frontend import ViewSBFrontend


class TUIFrontend(ViewSBFrontend):
    """ Text-based packet viewer for ViewSB. """

    UI_NAME = 'tui'
    UI_DESCRIPTION = 'interactive text-based UI'

    # Colorization options for each of the relevant widgets.
    # These are the simple ANSI options.
    COLOR_PALETTE = [
        ('body', 'white', 'black'),
        ('focus', 'light gray', 'dark blue', 'standout'),
        ('head', 'white', 'black', 'bold'),
        ('foot', 'light gray', 'black'),
        ('key', 'light cyan', 'black','underline'),
        ('title', 'white', 'black', 'bold'),
        ('header', 'light red', '', 'bold'),
        ('flag', 'dark gray', 'light gray'),
        ('error', 'dark red', ''),
        ('data', 'light blue', ''),
        ('key', 'light blue', 'black'),
        ('key_column', 'light blue', ''),
        ('okay', 'dark gray', ''),
        ('okay_focus', 'dark gray', 'dark blue'),

        ('error', 'light red', ''),
        ('error_focus', 'light red', 'dark blue'),

        ('icon',       'dark gray', ''),
        ('icon_focus', 'dark gray',  'dark blue'),

        ('popup', 'white', 'black'),
        ('popup_title', 'white', 'black', 'bold'),
        ('popup_error', 'light red', 'black', 'bold'),
        ('popup_summary', 'light gray', 'black'),
    ]

    # Mapping that maps normal/unfocused class names to their focused equivalents.
    FOCUSED_COLOR_MAPPINGS = {
        'padding': 'focus',
        'data':    'focus',
        'summary': 'focus',
        'okay':    'okay_focus',
        'error':   'error_focus',
        'icon':    'icon_focus',
    }

    # Initial footer text.
    DEFAULT_FOOTER_TEXT = [
        ('title', "ViewSB USB Analyzer"), "    ",
        ('key', "+"), "=expand ",
        ('key', "-"), "=collapse  ",
        ('key', "a"), "utoscroll ",
        ('key', "c"), "lear ",
        ('key', "q"), "uit ",
    ]

    # How often we poll the backend for new packets, in seconds.
    BACKGROUND_REFRESH_INTERVAL = 0.25


    @classmethod
    def add_options(cls, parser):
        """ Add command-line options for the TUI frontend. """

        parser.add_argument('--ascii-only', default=False, action='store_true',
            help="draw widgets with ASCII even on UTF-8 terminals (may improve rendering)")


    def __init__(self, ascii_only):
        """ Initializes the UI for the TUI widget. """

        super().__init__()
        self.ascii_only = ascii_only

        # For now: create a really inefficient in-memory packet store,
        # and anchor our tree-view to that.
        self.packet_store = TUIPacketCollection(self)
        self.root_node    = VSBRootNode(self.packet_store, self)

        # Generate the TreeList that's we'll use the display our packets.
        # This is the main viewport into the USB data.
        self.dynamic_view = urwid.TreeWalker(self.root_node)
        self.packet_list  = urwid.AttrWrap(PacketListBox(self.dynamic_view, self.packet_focus_changed), 'packets')
        self.packet_list.offset_rows = 1

        # Create the "decoded packet view" box.
        self.decoder_rows = urwid.SimpleListWalker([])
        decoder_rows_list = urwid.AttrWrap(urwid.ListBox(self.decoder_rows), 'decoder')

        # Create the "raw hex data" box.
        self.hex_data_rows = urwid.SimpleListWalker([])
        hexdump_rows_list = urwid.AttrWrap(urwid.ListBox(self.hex_data_rows), 'hexdump')

        # Right panel.
        right_panel = urwid.Pile([
            ('weight', 3, decoder_rows_list),
            ('pack', urwid.Text(('body', ""))),
            hexdump_rows_list
        ])

        # Create the outer UI chrome for our text UI.
        # TODO: generate the footer text dynamically?
        self.header  = VSBPacketWidget.get_row_headers(style='head')
        self.columns = urwid.Columns([('weight', 2, self.packet_list), right_panel], dividechars=1)
        self.footer  = urwid.Text(self.DEFAULT_FOOTER_TEXT)
        self.view    = urwid.Frame(
            body=urwid.AttrWrap(self.columns,  'body'),
            header=urwid.AttrWrap(self.header, 'head'),
            footer=urwid.AttrWrap(self.footer, 'foot'),
        )


    def packet_focus_changed(self, focused_packet_node, packet):
        """ Callback that's issued when the focused packet changes. """

        # Populate our ancillary packet views.
        self.populate_decoder_view(packet)
        self.populate_hex_view(packet)


    def populate_hex_view(self, packet):
        """ Populate the bottom-right panel with a hex dump of the given packet. """

        # TODO: auto-compute these based on the column width of our hex-list panel
        hex_row_width    = 8
        hex_column_ratio = 1

        # Start off with an empty hex view.
        self.hex_data_rows.clear()

        if packet is None or packet.get_raw_data is None:
            return

        data = packet.get_raw_data()

        # Iterate over our data, capturing it into row-length chunks.
        for i in range(0, len(data), hex_row_width):
            hex_bytes   = []
            ascii_bytes = []

            # Extract the data chunk we're looking for.
            chunk = data[i:i + hex_row_width]

            # Iterate over each byte in the given chunk.
            for byte in chunk:

                # Add the hex byte to our byte view...
                hex_bytes.append('{:02x}'.format(byte))

                # ... and add our ASCII summary.
                char = chr(byte)
                if char in string.ascii_letters + string.digits + string.punctuation:
                    ascii_bytes.append(char)
                else:
                    ascii_bytes.append('.')

            # Pad out the last row, for alignment.
            if len(chunk) < hex_row_width:
                for _ in range(0, hex_row_width - len(chunk)):
                    hex_bytes.append('  ')


            # Generate summaries in hex and ascii...
            hex_summary   = urwid.Text(' '.join(hex_bytes), align='right')
            ascii_summary = urwid.Text(''.join(ascii_bytes), align='left')


            # ... and add them to our view.
            row = urwid.Columns([
                ('weight', hex_column_ratio, hex_summary),
                ('weight', 1, ascii_summary),
            ], dividechars=1)
            self.hex_data_rows.append(row)



    def populate_decoder_view(self, packet):
        """ Populate the top-right panel with the decoded version of a given packet. """

        # Start off with an empty decoder view.
        self.decoder_rows.clear()

        if packet is None:
            return

        fields = packet.get_detail_fields()

        if not fields:
            return

        # Render each table in the detail fields.
        for table_name, contents in fields:

            # Render the table name, and its contents.
            self.decoder_rows.append(urwid.Text(('header', table_name)))

            if isinstance(contents, collections.Mapping):
                self.add_key_value_table_to_decoder_view(contents)
            elif isinstance(contents, str):
                self.add_string_to_decoder_view(contents)
            elif isinstance(contents, bytes):
                self.add_hexdump_to_decoder_view(contents)
            elif isinstance(contents, collections.Sequence):
                self.add_single_column_table_to_decoder_view(contents)
            else:
                self.add_string_to_decoder_view(
                    "decoder error: unknown how to render type {}".format(type(contents).__name__),
                    style='error')

            # Render a spacer after each table.
            self.decoder_rows.append(urwid.Text(('spacer', '')))


    def add_hexdump_to_decoder_view(self, contents):
        # FIXME: implement
        self.add_string_to_decoder_view(repr(contents))


    def add_single_column_table_to_decoder_view(self, table):
        """ Adds a decoder-result table to the decoder panel on the right. """

        for entry in table:
            self.add_string_to_decoder_view(entry)



    def add_string_to_decoder_view(self, string, style=''):
        """ Adds a string to the sequence of decoder view widgets. """

        # Create a string that's padded from the edges, and wrapped in a style.
        self.decoder_rows.append(self.format_string_for_view(string, style))


    def format_string_for_view(self, string, style='', padding=1):
        """
        Wraps a given string in a stack of UI elements; preparing it to be added to
        a display table.
        """

        string = urwid.Text(('value_name', string))
        string = urwid.Padding(string, left=padding, right=padding)
        string = urwid.AttrWrap(string, style)

        return string


    def add_key_value_table_to_decoder_view(self, table, padding=1):
        """ Adds a decoder-result table to the decoder panel on the right. """

        # Add each key/value pair to our table.
        for key, value in table.items():
            if isinstance(value, dict):
                self.decoder_rows.append(self.format_string_for_view(str(key), style='key_column'))
                self.add_key_value_table_to_decoder_view(value, padding=padding + 2)
            else:
                columns = urwid.Columns([
                    self.format_string_for_view(str(key), style='key_column', padding=padding),
                    self.format_string_for_view(str(value))
                ])
                self.decoder_rows.append(columns)


    def handle_communications(self):
        """ Function that is called to check the analyzer for new packets. """

        # Handle exceptions
        if self._exception_conn.poll():
            self.handle_exception(*self._exception_conn.recv())

        # Hook the analyzer to automatically schedule a subsequent communication each time
        # we check for packets.
        super().handle_communications()
        self.schedule_next_communication()


    def schedule_next_communication(self):
        """ Schedules the next comms check; which handles periodic loading of received packets into the UI. """

        # Ask the main loop to call our comms handler after a REFRESH_INTERVAL delay.
        self.loop.set_alarm_in(self.BACKGROUND_REFRESH_INTERVAL, lambda _, __ : self.handle_communications())


    def handle_incoming_packet(self, packet):
        """ Pass any incoming packets to our packet collection. """

        # Add the packet to our packet collection...
        self.root_node.add_packet(packet)

        # If we're in autoscroll mode, handle autoscrolling.
        if self.packet_list.autoscroll:

            # Handle scrolling as if the user hit the END key.
            # This keeps the logic relatively consistent, and meshes into urwid's event model.
            self.loop.process_input(['end', 'a'])


    def unhandled_input(self, key):
        """ Handle any input that's not handled by e.g. the focused widget. """

        if key == 'c':
            self.packet_list.original_widget.body.set_focus(self.root_node) # idk why it needs this
            self.packet_list.original_widget.focus_position = self.root_node
            self.packet_list.original_widget.autoscroll = True
            self.packet_focus_changed(None, None)

            self.root_node.remove_all_packets()

        elif key in ('q', 'Q'):
            raise urwid.ExitMainLoop()


    def handle_exception(self, exception, traceback):
        """Override the default implementation to properly show exceptions with urwid"""
        popup = ExceptionDialog('Oops, we received an error from the backend!', traceback)
        self.loop.widget = urwid.Overlay(
            popup,
            self.loop.widget,
            align='center',
            valign='middle',
            width=100,
            height=popup.height,
        )
        def close_popup(button):
            self.loop.widget = self.loop.widget.bottom_w
        urwid.connect_signal(popup, 'close', close_popup)

    def run(self):
        """Run the frontend."""

        # Create the main event-loop that will run all of our stuff.
        self.loop = urwid.MainLoop(self.view, self.COLOR_PALETTE, unhandled_input=self.unhandled_input)

        # Restore the terminal's input capabilities; as Python rudely closed the stdin
        # that we were working with. We've voluntarily closed it on all other processes,
        # so we can feel free to just take it back, here.
        self.loop.screen._term_input_file = self.stdin

        # Run the main TUI.
        self.schedule_next_communication()
        try:
            self.loop.run()
        except KeyboardInterrupt:
            pass

        # FIXME: signal for termination, here?


class ExceptionDialog(urwid.WidgetWrap):
    """A dialog that appears with an exception is thrown"""
    signals = ['close']

    def __init__(self, title, text):
        self.height = len(text.split('\n')) + 2
        close_button = urwid.Button('Close')
        urwid.connect_signal(
            close_button,
            'click',
            lambda button: self._emit('close'),
        )
        pile = urwid.Pile([
            urwid.AttrWrap(urwid.Text(title), 'popup_error'),
            urwid.AttrWrap(urwid.Text(text), 'popup_summary'),
            close_button,
        ])
        fill = urwid.Filler(pile)
        self.__super.__init__(urwid.AttrWrap(fill, 'popup'))


class PacketListBox(urwid.TreeListBox):

    def __init__(self, walker, focus_changed_callback=None):

        # Start off with no previously-focused element.
        self.last_focus = False

        # Register our focus-changed callback.
        self.focus_changed_callback = focus_changed_callback

        # Autoscroll by default.
        self.autoscroll = True

        super().__init__(walker)


    def focus_changed(self):
        """ Called when the focus may have changed; handles focus-change event generation. """

        # Get the currently focused node, and re-render it with focus.
        focused_node = self.focus.get_node()
        focused_node.rerender_with_focus(True)

        # If we have a "focus changed" callback, call it.
        if callable(self.focus_changed_callback):
            self.focus_changed_callback(focused_node, focused_node.get_value())

        # If we had a previously focused node, let it know it's no longer focused.
        if self.last_focus and self.last_focus != focused_node:
            self.last_focus.rerender_with_focus(False)

        # And update our previously-focused-node.
        self.last_focus = focused_node


    def keypress(self, size, key):
        """ Keypress interposer that issues the "focus change detect" code after a keypress. """

        vim_mappings = {
            'h': 'left',
            'j': 'down',
            'k': 'up',
            'l': 'right'
        }

        # Once the user's interacted with the widget, disable autoscroll.
        self.autoscroll = False

        # If we have a vim-mapping for our keys, translate it.
        if key in vim_mappings.keys():
            key = vim_mappings[key]

        if key == 'home':
            self.focus_home(size)
        elif key == 'end':
            self.focus_end(size)
        elif key == 'a':
            self.autoscroll = True
        else:
            key = self.__super.keypress(size, key)
            key = self.unhandled_input(size, key)

        # Check for a focus change, which can be triggered by a keypress.
        self.focus_changed()

        # Don't modify the keypress.
        return key


    def mouse_event(self, *args, **kwargs):
        """ Mouse event interposer that issues the "focus change detect" code after a mouse event. """

        # Call the parent function...
        result = super().mouse_event(*args, **kwargs)

        # ... and once it's finished, check for a focus change.
        self.focus_changed()

        # Return the mouse event unmodified.
        return result


    def get_focused_packet(self):
        """ Returns the packet for the element currently in focus. """

        focused_node = self.focus.get_node()
        return focused_node.get_value()




class VSBPacketNode(urwid.ParentNode):
    """ Data storage object for interior/parent nodes. """


    def __init__(self, packet_store, frontend, *args, **kwargs):
        self.frontend = frontend
        super().__init__(packet_store, *args, **kwargs)


    def _invalidate(self):
        """ Mark the current node as requiring a re-render. """
        self.frontend.dynamic_view._modified()


    def rerender_with_focus(self, focus):
        """ Re-render the given node with or without focus."""

        if focus:
            self._widget = self._highlighted_widget
        else:
            self._widget = self._unhighlighted_widget


    def next_key(self):
        if self._child_keys:
            return len(self._child_keys)
        else:
            return 0


    def add_packet(self, packet):
        if self._child_keys:
            self._child_keys.append(self.next_key())
        else:
            self._child_keys = [self.next_key()]

        self.get_value().accept_packet(packet)
        self._invalidate()


    def remove_all_packets(self):
        self.get_value().clear_packets()
        self._child_keys = []
        self._invalidate()


    def load_widget(self):
        """ Returns the widget used to render the current icon. """

        self._unhighlighted_widget = VSBPacketWidget(self, self.get_value(), self.frontend)
        self._highlighted_widget   = urwid.AttrWrap(
                urwid.AttrWrap(self._unhighlighted_widget, 'focus'),
                TUIFrontend.FOCUSED_COLOR_MAPPINGS
            )
        return self._unhighlighted_widget


    def load_child_keys(self):
        """ Return all of the child packet indices for the given node. """

        # Our child packets are just organized into a list,
        # so we can just return a range of the same length as our list.
        packet = self.get_value()
        return list(range(len(packet.subordinate_packets)))


    def get_child_keys(self):
        return self.load_child_keys()


    def load_child_node(self, key):
        """ Converts a subordinate packet into a display line object. """

        # Look up this parent's child node
        packet = self.get_value()
        child  = packet.subordinate_packets[key]

        # Our children are always one level deeper than we are.
        child_depth = self.get_depth() + 1

        # Return the relevant packet, wrapped in a Tree Node object.
        return VSBPacketNode(child, self.frontend, parent=self, key=key, depth=child_depth)


class VSBPacketWidget(urwid.TreeWidget):
    """ Widget that renders tree elements as text. """

    # If we're in utf8 mode, use fancier widgets than we would in ASCII mode.
    UTF8_ICONS = {
        'unexpanded': urwid.SelectableIcon('⊞', 0),
        'expanded':   urwid.SelectableIcon('⊟', 0),
        'leaf':       urwid.Text('•'),
        'in':         urwid.Text(('data', '↩  IN')),
        'out':        urwid.Text(('data', 'OUT ↪')),
    }

    ASCII_ICONS = {
        'unexpanded': urwid.SelectableIcon('+', 0),
        'expanded':   urwid.SelectableIcon('-', 0),
        'leaf':       urwid.Text('*'),
        'in':         urwid.Text('<I'),
        'out':        urwid.Text('O>')
    }


    def __init__(self, parent, packet, frontend, focused=False):

        self.packet = packet
        self.frontend = frontend
        self.is_root = False
        self.focused = focused

        if urwid.get_encoding_mode() == "utf8" and not frontend.ascii_only:
            self.ICONS = self.UTF8_ICONS
        else:
            self.ICONS = self.ASCII_ICONS

        super().__init__(parent)

        self.expanded = False
        self.is_leaf = not packet.subordinate_packets
        self._wrapped_widget = self.get_row_widget()


    def get_icon(self):
        """ Retrieve the icon to display whether the node can be expanded or collapsed. """

        # If we have a leaf, render it's single state icon.
        if self.is_leaf:
            icon = self.ICONS['leaf']
        # If we have a parent, return the icon corresponding to its expanded state.
        else:
            icon = self.ICONS['expanded'] if self.expanded else self.ICONS['unexpanded']

        return urwid.AttrWrap(icon, 'icon')


    def update_expanded_icon(self):
        self.core_widget.widget_list[0] = self.get_icon()


    @classmethod
    def _get_text_column(cls, value, style='summary', autohex=True, width=None, weighted=False, align='left', empty='--'):

        if value is None:
            value = empty

        if autohex and isinstance(value, int):
            value = "{:x}".format(value)

        # ... wrap it with a text object...
        widget = urwid.Text((style, str(value)), align=align)

        # ... optionally add a width for urwid.Columns...
        if width is not None:
            if weighted:
                widget = ('weight', width, widget)
            else:
                widget = (width, widget)

        # ... and return the new widget.
        return widget


    def _get_direction_icon(self, direction, width=6):

        if direction == USBDirection.IN:
            return (width, self.ICONS['in'])
        elif direction == USBDirection.OUT:
            return (width, self.ICONS['out'])
        else:
            return (width, urwid.Text(""))


    @classmethod
    def get_row_headers(cls, style=''):
        """ Returns a columns object suitable for column headers."""

        return urwid.Columns([
            #cls._get_text_column('Bus',    style=style, width=3),
            cls._get_text_column('Dev',    style=style, width=3),
            cls._get_text_column('EP',     style=style, width=3),
            cls._get_text_column('Dir',    style=style, width=6),
            cls._get_text_column('Len',    style=style, width=5),
            cls._get_text_column('   Packet', style=style)
        ], dividechars=1)



    def get_row_widget(self):
        """ Returns the widget that represents the given packet. """

        # Get a quick reference to our core packet.
        packet = self.packet

        if packet.get_summary_fields is None:
            return urwid.Text("")

        summary = packet.get_summary_fields()

        # Generate the style for our packet's style.
        status_style = 'okay'
        if summary['style'] and ('exceptional' in summary['style']):
            status_style = 'error'

        # Get the fields of our packet entry.
        return urwid.Columns([
            #self._get_text_column(summary['bus_number'],      width=3),
            self._get_text_column(summary['device_address'],  width=3),
            self._get_text_column(summary['endpoint'],        width=3),
            self._get_direction_icon(summary['is_in']),
            self._get_text_column(summary['length'], autohex=False, width=5, empty=''),
            self.get_indented_core(),
            self._get_text_column(summary['status'], style=status_style, width=6, align='center'),
            self._get_text_column(summary['data_summary'], style='data')
        ], dividechars=1)


    def get_indented_core(self):
        widget = self.get_inner_widget()
        icon   = ('fixed', 1, self.get_icon())

        self.core_widget = urwid.Columns([icon, widget], dividechars=1)

        indent_cols = self.get_indent_cols()
        return urwid.Padding(self.core_widget, width=('relative', 100), left=indent_cols + 1)


    def prev_inorder(self):

        # Use the normal algorithm to identify our predecessor...
        prev = super().prev_inorder()

        # .. but if the previous would be our root widget, return none.
        # This ensures we never select the invisible root widget.
        if isinstance(prev, VSBRootNode.NonDisplayingWidget):
            return None
        else:
            return prev


    def get_display_text(self):
        return [('summary', self.packet.summarize())]

    def selectable(self):
        # Always allow our packets to be selectable, so the user can
        # get more analysis information.
        return True


    def get_indent_cols(self):
        return self.indent_cols * (self.get_node().get_depth() - 1)


class VSBRootNode(VSBPacketNode):
    """
    Special case of VSBPacketNode that renders the invisible root node --
    the utility node that contains all other nodes.
    """

    class NonDisplayingWidget(VSBPacketWidget):
        """ Special class for the non-displaying root node. """

        def __init__(self, *args, **kwargs):
            super().__init__(*args, *kwargs)
            self.is_leaf = False
            self.expanded = True


        def rows(self, *args, **kwargs):
            # Return a widget that takes zero rows; and thus will be skipped during
            # listbox render.
            return 0


        def render(self, size, focus=False ):
            return urwid.SolidCanvas(" ", *size, 0)


        def selectable(self):
            return False


    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.expanded = True
        self._widget = self.NonDisplayingWidget(self, self.get_value(), self.frontend)

    def is_root(self):
        return True

    def rerender_with_focus(self, focus):
        return

    def get_widget(self):
        return self._widget






class TUIPacketCollection:
    """ Simple collection of displayed packets for ourTUI. """

    def __init__(self, frontend):

        self.data = None

        # Store the packet_list associated with this collection.
        self.frontend = frontend

        # Start off with an empty list of subordinate packets.
        self.subordinate_packets = []

    def clear_packets(self):
        self.subordinate_packets = []

    def accept_packet(self, packet):
        """ Accepts a new subordinate packet into the collection. """
        self.subordinate_packets.append(packet)

    def summarize(self):
        return "New Capture ({}):".format(len(self.subordinate_packets))

    def summarize_data(self):
        return None

    def summarize_status(self):
        return None

    def get_detail_fields(self):
        return []


    def __getattr__(self, attr):
        return None
