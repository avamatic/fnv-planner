"""Selected entities widget scaffold."""

from gi.repository import Gtk


class SelectedEntitiesView(Gtk.Box):
    """Placeholder selected entities widget."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        label = Gtk.Label(label="Selected perks/traits/gear will appear here.")
        label.set_xalign(0)
        self.append(label)

