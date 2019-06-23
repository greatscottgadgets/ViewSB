"""
Quick experiment with a TUI frontend
"""

import os
import urwid
import collections

from urwid.widget import Widget
from ..frontend import ViewSBFrontend


class TUIFrontend(ViewSBFrontend):
    """ Text-based packet viewer for ViewSB. """


    # Colorization options for each of the relevant widgets.
    # These are the simple ANSI options.
    COLOR_PALETTE = [
        ('body', 'white', 'black'),
        ('focus', 'light gray', 'dark blue', 'standout'),
        ('head', 'yellow', 'black', 'standout'),
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
    ]


    # Initial footer text.
    DEFAULT_FOOTER_TEXT = [
        ('title', "capture running"), "    ",
        ('key', "UP"), ",", ('key', "DOWN"), ",",
        ('key', "PAGE UP"), ",", ('key', "PAGE DOWN"),
        "  ",
        ('key', "+"), ",",
        ('key', "-"), "  ",
        ('key', "LEFT"), "  ",
        ('key', "HOME"), "  ",
        ('key', "END"), "  ",
        ('key', "Q"),
    ]

    # Default title for a ViewSB TUI.
    DEFAULT_VIEW_TITLE = " ViewSB -- connected -- using magic text-UI frontend"

    # How often we poll the backend for new packets, in seconds.
    BACKGROUND_REFRESH_INTERVAL = 0.25


    def __init__(self, title=None):
        """ Initializes the UI for the TUI widget. """

        # If no title is provided, use the default one.
        if title is None:
            title = self.DEFAULT_VIEW_TITLE

        # For now: create a really inefficient in-memory packet store,
        # and anchor our tree-view to that.
        self.packet_store = TUIPacketCollection(self)
        self.root_node    = VSBPacketNode(self.packet_store, self)

        # Generate the TreeList that's we'll use the display our packets.
        # This is the main viewport into the USB data.
        self.dynamic_view = urwid.TreeWalker(self.root_node)
        self.packet_list  = urwid.AttrWrap(PacketListBox(self.dynamic_view, self.packet_focus_changed), 'packets')
        self.packet_list.offset_rows = 1

        # Create the "decoded packet view" box.
        self.decoder_rows = urwid.SimpleListWalker([])
        decoder_rows_list = urwid.AttrWrap(urwid.ListBox(self.decoder_rows), 'decoder')

        # Create the outer UI chrome for our text UI.
        # TODO: generate the footer text dynamically?
        self.header  = urwid.Text("  " + title)
        self.columns = urwid.Columns([('weight', 2, self.packet_list), decoder_rows_list], dividechars=1)
        self.footer  = urwid.Text(self.DEFAULT_FOOTER_TEXT)
        self.view    = urwid.Frame(
            body=urwid.AttrWrap(self.columns, 'body'),
            header=urwid.AttrWrap(self.header, 'head'),
            footer=urwid.AttrWrap(self.footer, 'foot'),
        )


    def packet_focus_changed(self, focused_packet_node, packet):
        """ Callback that's issued when the focused packet changes. """

        # Populate our ancillary packet views.
        self.populate_decoder_view(packet)


    def populate_decoder_view(self, packet):
        """ Populate the right-hand panel with the decoded version of a given packet. """

        fields = packet.get_detail_fields()

        # Start off with an empty decoder view.
        self.decoder_rows.clear()

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


    def add_key_value_table_to_decoder_view(self, table):
        """ Adds a decoder-result table to the decoder panel on the right. """

        # Add each key/value pair to our table.
        for key, value in table.items():
            columns = urwid.Columns([
                self.format_string_for_view(str(key), style='key_column'),
                self.format_string_for_view(str(value))
            ])
            self.decoder_rows.append(columns)


    def handle_communications(self):
        """ Function that is called to check the analyzer for new packets. """

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
        self.root_node.add_packet(packet)



    def unhandled_input(self, k):
        """ Handle any input that's not handled by e.g. the focused widget. """

        if k in 'qQ':
            raise urwid.ExitMainLoop()


    def run(self):
        """Run the frontend."""

        # Create the main event-loop that will run all of our stuff.
        self.loop = urwid.MainLoop(self.view, self.COLOR_PALETTE, unhandled_input=self.unhandled_input)

        # Restore the terminat's input capabilities; as Python rudely closed the stdin
        # that we were working with. We've voluntarily closed it on all other processes,
        # so we can feel free to just take it back, here.
        self.loop.screen._term_input_file = self.stdin

        # Run the main TUI.
        self.schedule_next_communication()
        self.loop.run()

        # FIXME: signal for termination, here?



class PacketListBox(urwid.TreeListBox):

    def __init__(self, walker, focus_changed_callback=None):

        # Start off with no previously-focused element.
        self.last_focus = False
        
        # Register our focus-changed callback.
        self.focus_changed_callback = focus_changed_callback

        super().__init__(walker)


    def focus_changed(self):
        """ Called when the focus may have changed; handles focus-change event generation. """
 
        #if self.focus is self.last_focus:
        #    return

        # Get the currently focused node, and re-render it with focus.
        focused_node = self.focus.get_node()
        focused_node.rerender_with_focus(True)

        # If we have a "focus changed" callback, call it.
        if callable(self.focus_changed_callback):
            self.focus_changed_callback(focused_node, focused_node.get_value())
        
        # If we had a previously focused node, let it know it's no longer focused.
        if self.last_focus:
            self.last_focus.rerender_with_focus(False)

        # And update our previously-focused-node.
        self.last_focus = focused_node


    def keypress(self, size, key):
        """ Keypress interposer that issues the "focus change detect" code after a keypress. """

        # Issue keypresses to our superclass, which notifies its widgets.
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
    """ Data storage object for interior/parent nodes """


    def __init__(self, packet_store, frontend, *args, **kwargs):
        self.frontend = frontend
        super().__init__(packet_store, *args, **kwargs)


    def _invalidate(self):
        #self.get_widget(reload=True)
        self.frontend.dynamic_view._modified()


    def rerender_with_focus(self, focus):
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


    def load_widget(self):
        """ Returns the widget used to render the current icon. """
        self._unhighlighted_widget = VSBPacketWidget(self, self.get_value(), self.frontend)
        self._highlighted_widget   = urwid.AttrWrap(urwid.AttrWrap(self._unhighlighted_widget, 'focus'), 
                {'padding': 'focus', 'data': 'focus', 'summary': 'focus', 'okay': 'okay_focus', 'error': 'error_focus'} )
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

    def __init__(self, parent, packet, frontend, focused=False):

        self.packet = packet
        self.frontend = frontend
        self.is_root = parent.is_root()
        self.focused = focused

        super().__init__(parent)

        has_children = len(packet.subordinate_packets) > 0

        self.expanded = self.is_root
        self.is_leaf = not (has_children or self.is_root)


    def get_display_text(self):
        packet = self.packet
        text = [('summary', packet.summarize())]


        try:
            status_summary = packet.summarize_status()
            
            # XXX temporary horrorhack -- use .style instead
            style = 'error' if ('STALL' in status_summary) else 'okay'

            # TODO: color me per the actual status (style=error?)
            text.append((style, " " + status_summary))
        except:
            pass

        if packet.data:
            text.append(('padding', '  '))

            data = ('data', " [{}]".format(packet.summarize_data()))
            text.append(data)


        return text

    def selectable(self):
        # Always allow our packets to be selectable, so the user can
        # get more analysis information.
        return True



class TUIPacketCollection:
    """ Simple collection of displayed packets for TUI. """

    def __init__(self, frontend):

        self.data = None

        # Store the packet_list associated with this collection.
        self.frontend = frontend

        # Start off with an empty list of subordinate packets.
        self.subordinate_packets = []


    def accept_packet(self, packet):
        """ Accepts a new subordinate packet into the collection. """
        self.subordinate_packets.append(packet)

    def summarize(self):
        return "New Capture ({}):".format(len(self.subordinate_packets))

    def get_detail_fields(self):
        return []
