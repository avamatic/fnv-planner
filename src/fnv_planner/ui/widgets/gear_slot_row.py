"""Gear-slot row widget scaffold."""

from gi.repository import Gtk


class GearSlotRow(Gtk.Box):
    """Simple row showing slot name + current item."""

    def __init__(self, slot_name: str, item_name: str = "(empty)") -> None:
        super().__init__(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        slot = Gtk.Label(label=slot_name)
        slot.set_xalign(0)
        item = Gtk.Label(label=item_name)
        item.set_xalign(0)
        item.set_hexpand(True)
        self.append(slot)
        self.append(item)

