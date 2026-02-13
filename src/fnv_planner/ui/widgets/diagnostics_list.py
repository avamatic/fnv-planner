"""Diagnostics list widget scaffold."""

from gi.repository import Gtk


class DiagnosticsList(Gtk.Box):
    """Placeholder diagnostics widget."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        label = Gtk.Label(label="Diagnostics will appear here.")
        label.set_xalign(0)
        self.append(label)

