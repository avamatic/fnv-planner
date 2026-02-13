"""Library page view."""

from gi.repository import Gtk

from fnv_planner.engine.ui_model import CatalogItem
from fnv_planner.ui.controllers.library_controller import LibraryController


class LibraryPage(Gtk.Box):
    """Library browser for gear search, inspect, equip, and removal."""

    def __init__(self, controller: LibraryController) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._controller = controller
        self._updating = False
        self._rows_by_key: dict[str, CatalogItem] = {}
        self._active_key: str | None = None
        self._selected_zone: str = "all"
        self._zone_to_slots: dict[str, set[int]] = {
            "all": set(),
            "head": {8},
            "face": {0},
            "torso": {7},
            "hands": {2, 3, 4},
            "back": {1},
            "belt": {5, 6},
        }

        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(16)
        self.set_margin_end(16)
        self.set_hexpand(True)
        self.set_vexpand(True)

        title = Gtk.Label(label="Library")
        title.add_css_class("title-2")
        title.set_xalign(0)
        self.append(title)

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.append(controls)

        self._search = Gtk.SearchEntry()
        self._search.set_placeholder_text("Search gear...")
        self._search.set_hexpand(True)
        self._search.connect("search-changed", self._on_filter_changed)
        controls.append(self._search)

        self._armor_toggle = Gtk.CheckButton(label="Armor")
        self._armor_toggle.set_active(True)
        self._armor_toggle.connect("toggled", self._on_filter_changed)
        controls.append(self._armor_toggle)

        self._weapon_toggle = Gtk.CheckButton(label="Weapons")
        self._weapon_toggle.set_active(True)
        self._weapon_toggle.connect("toggled", self._on_filter_changed)
        controls.append(self._weapon_toggle)

        self._status_label = Gtk.Label(xalign=0)
        self._status_label.add_css_class("error")
        self.append(self._status_label)

        body_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        body_row.set_hexpand(True)
        body_row.set_vexpand(True)
        self.append(body_row)

        body_filter = self._build_body_filter()
        body_row.append(body_filter)

        split = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        split.set_wide_handle(True)
        split.set_shrink_start_child(False)
        split.set_shrink_end_child(False)
        split.set_hexpand(True)
        split.set_vexpand(True)
        body_row.append(split)

        list_frame = Gtk.Frame(label="Gear Catalog")
        split.set_start_child(list_frame)
        list_scroll = Gtk.ScrolledWindow()
        list_scroll.set_min_content_width(500)
        list_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        list_frame.set_child(list_scroll)
        self._catalog_list = Gtk.ListBox()
        self._catalog_list.connect("row-selected", self._on_catalog_row_selected)
        list_scroll.set_child(self._catalog_list)

        inspector_frame = Gtk.Frame(label="Inspector")
        split.set_end_child(inspector_frame)
        inspector = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        inspector.set_margin_top(10)
        inspector.set_margin_bottom(10)
        inspector.set_margin_start(10)
        inspector.set_margin_end(10)
        inspector_frame.set_child(inspector)

        self._name_label = Gtk.Label(label="Select an item", xalign=0)
        self._name_label.add_css_class("title-4")
        self._name_label.set_wrap(True)
        inspector.append(self._name_label)

        self._meta_label = Gtk.Label(xalign=0)
        self._meta_label.set_wrap(True)
        inspector.append(self._meta_label)

        self._effects_label = Gtk.Label(xalign=0)
        self._effects_label.set_wrap(True)
        inspector.append(self._effects_label)

        action_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        inspector.append(action_row)
        self._equip_button = Gtk.Button(label="Equip")
        self._equip_button.connect("clicked", self._on_equip_clicked)
        action_row.append(self._equip_button)

        self._clear_slot_button = Gtk.Button(label="Clear Slot")
        self._clear_slot_button.connect("clicked", self._on_clear_slot_clicked)
        action_row.append(self._clear_slot_button)

        equipped_frame = Gtk.Frame(label="Equipped by Slot")
        inspector.append(equipped_frame)
        equipped_scroll = Gtk.ScrolledWindow()
        equipped_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        equipped_scroll.set_min_content_height(180)
        equipped_frame.set_child(equipped_scroll)
        self._equipped_list = Gtk.ListBox()
        equipped_scroll.set_child(self._equipped_list)

        # Activate default zone only after catalog widgets are initialized.
        self._zone_buttons["all"].set_active(True)
        self.refresh()

    def _build_body_filter(self) -> Gtk.Widget:
        frame = Gtk.Frame(label="Body Filter")
        frame.set_size_request(180, -1)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        box.set_margin_top(10)
        box.set_margin_bottom(10)
        box.set_margin_start(10)
        box.set_margin_end(10)
        frame.set_child(box)

        self._zone_label = Gtk.Label(label="Zone: All", xalign=0)
        box.append(self._zone_label)

        fixed = Gtk.Fixed()
        fixed.set_size_request(180, 320)
        box.append(fixed)

        self._zone_buttons: dict[str, Gtk.ToggleButton] = {}
        anchor: Gtk.ToggleButton | None = None
        zone_specs = [
            ("all", "All", 66, 2),
            ("head", "Head", 66, 44),
            ("face", "Face", 66, 84),
            ("torso", "Torso", 58, 130),
            ("hands", "Hands", 56, 190),
            ("back", "Back", 64, 236),
            ("belt", "Belt", 66, 276),
        ]
        for zone, label, x, y in zone_specs:
            btn = Gtk.ToggleButton(label=label)
            btn.set_size_request(64, 30)
            if anchor is None:
                anchor = btn
            else:
                btn.set_group(anchor)
            btn.connect("toggled", self._on_zone_toggled, zone)
            fixed.put(btn, x, y)
            self._zone_buttons[zone] = btn

        return frame

    def refresh(self) -> None:
        self._controller.refresh()
        self._updating = True
        try:
            self._render_catalog()
            self._render_equipped()
            self._render_inspector()
        finally:
            self._updating = False

    def _render_catalog(self) -> None:
        self._clear_list(self._catalog_list)
        self._rows_by_key = {}

        items = self._controller.catalog_items(
            query=self._search.get_text(),
            include_armor=self._armor_toggle.get_active(),
            include_weapons=self._weapon_toggle.get_active(),
        )
        allowed_slots = self._zone_to_slots.get(self._selected_zone, set())
        if allowed_slots:
            items = [it for it in items if it.slot in allowed_slots]
        for item in items:
            key = f"{item.kind}:{item.form_id:x}"
            self._rows_by_key[key] = item
            line = (
                f"{item.kind:<6}  {item.name}  "
                f"(slot {item.slot}, value {item.value}, wt {item.weight:.1f})"
            )
            row = Gtk.ListBoxRow()
            row.set_selectable(True)
            row.set_activatable(True)
            row.set_child(Gtk.Label(label=line, xalign=0))
            row.set_tooltip_text(key)
            self._catalog_list.append(row)
            if key == self._active_key:
                self._catalog_list.select_row(row)

        if not items:
            row = Gtk.ListBoxRow()
            row.set_child(Gtk.Label(label="No matching items.", xalign=0))
            self._catalog_list.append(row)

    def _render_equipped(self) -> None:
        self._clear_list(self._equipped_list)
        equipped = self._controller.equipped_slots()
        if not equipped:
            row = Gtk.ListBoxRow()
            row.set_child(Gtk.Label(label="No equipped items.", xalign=0))
            self._equipped_list.append(row)
            return
        for slot, form_id, name in equipped:
            row = Gtk.ListBoxRow()
            row.set_child(
                Gtk.Label(
                    label=f"Slot {slot}: {name} ({form_id:#x})",
                    xalign=0,
                    wrap=True,
                )
            )
            self._equipped_list.append(row)

    def _render_inspector(self) -> None:
        item = self._active_item()
        if item is None:
            self._name_label.set_text("Select an item")
            self._meta_label.set_text("")
            self._effects_label.set_text("")
            self._equip_button.set_sensitive(False)
            self._clear_slot_button.set_sensitive(False)
            return

        self._name_label.set_text(item.name)
        self._meta_label.set_text(
            f"{item.kind} | form {item.form_id:#x} | slot {item.slot} | "
            f"value {item.value} | weight {item.weight:.1f}"
        )
        model = self._controller.get_item(item.form_id)
        if model is None or not model.stat_effects:
            self._effects_label.set_text("Effects: none")
        else:
            lines = ["Effects:"]
            for effect in model.stat_effects:
                lines.append(f"- {self._controller.format_effect(effect)}")
            self._effects_label.set_text("\n".join(lines))
        self._equip_button.set_sensitive(True)
        self._clear_slot_button.set_sensitive(True)

    def _active_item(self) -> CatalogItem | None:
        if self._active_key is None:
            return None
        return self._rows_by_key.get(self._active_key)

    def _on_filter_changed(self, _widget: Gtk.Widget) -> None:
        if self._updating:
            return
        self.refresh()

    def _on_zone_toggled(
        self,
        button: Gtk.ToggleButton,
        zone: str,
    ) -> None:
        if self._updating or not button.get_active():
            return
        if not hasattr(self, "_catalog_list"):
            return
        self._selected_zone = zone
        self._zone_label.set_text(f"Zone: {zone.capitalize()}")
        self._active_key = None
        self._status_label.set_text("")
        self.refresh()

    def _on_catalog_row_selected(self, _list: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        if row is None or self._updating:
            return
        key = row.get_tooltip_text() or ""
        if key not in self._rows_by_key:
            return
        self._active_key = key
        self._status_label.set_text("")
        self._render_inspector()

    def _on_equip_clicked(self, _button: Gtk.Button) -> None:
        item = self._active_item()
        if item is None:
            return
        ok, message = self._controller.equip_catalog_item(item)
        self._status_label.set_text("" if ok else (message or "Could not equip item"))
        self.refresh()

    def _on_clear_slot_clicked(self, _button: Gtk.Button) -> None:
        item = self._active_item()
        if item is None:
            return
        ok, message = self._controller.clear_slot(item.slot)
        self._status_label.set_text("" if ok else (message or "Could not clear slot"))
        self.refresh()

    def _clear_list(self, listbox: Gtk.ListBox) -> None:
        child = listbox.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            listbox.remove(child)
            child = next_child
