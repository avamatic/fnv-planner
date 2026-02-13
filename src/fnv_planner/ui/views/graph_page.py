"""Perk graph ('Cool Stuff') page scaffold."""

from gi.repository import Gtk


class GraphPage(Gtk.Box):
    """Placeholder graph screen."""

    def __init__(self) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(16)
        self.set_margin_end(16)

        title = Gtk.Label(label="Cool Stuff")
        title.add_css_class("title-2")
        title.set_xalign(0)
        self.append(title)

        body = Gtk.Label(
            label=(
                "Perk graph scaffold.\n"
                "Next: level-aware node states, requirements, and path highlighting."
            )
        )
        body.set_xalign(0)
        body.set_wrap(True)
        self.append(body)
