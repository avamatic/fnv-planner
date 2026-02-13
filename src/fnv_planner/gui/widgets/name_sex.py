"""Name and sex input group."""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

if TYPE_CHECKING:
    from fnv_planner.gui.session import SessionManager
    from fnv_planner.gui.window import FnvPlannerWindow


class NameSexGroup(Adw.PreferencesGroup):
    __gtype_name__ = "NameSexGroup"

    def __init__(
        self,
        session: SessionManager,
        window: FnvPlannerWindow,
    ) -> None:
        super().__init__(title="Identity")
        self._session = session
        self._window = window

        # -- Name entry -------------------------------------------------------
        self._name_row = Adw.EntryRow(title="Name")
        self._name_row.set_text(session.name)
        self._name_row.connect("notify::text", self._on_name_changed)
        self.add(self._name_row)

        # -- Sex combo --------------------------------------------------------
        self._sex_model = Gtk.StringList.new(["Male", "Female"])
        self._sex_row = Adw.ComboRow(title="Sex", model=self._sex_model)
        if session.sex is not None:
            self._sex_row.set_selected(session.sex)
        self._sex_row.connect("notify::selected", self._on_sex_changed)
        self.add(self._sex_row)

    def _on_name_changed(self, row: Adw.EntryRow, _pspec: object) -> None:
        self._session.set_name(row.get_text())

    def _on_sex_changed(self, row: Adw.ComboRow, _pspec: object) -> None:
        selected = row.get_selected()
        if selected != Gtk.INVALID_LIST_POSITION:
            self._session.set_sex(selected)
            self._window.emit("stats-changed")
