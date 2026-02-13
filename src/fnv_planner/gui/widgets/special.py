"""S.P.E.C.I.A.L. allocation group with SpinRows and budget label."""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk  # noqa: E402

from fnv_planner.models.constants import (  # noqa: E402
    ACTOR_VALUE_NAMES,
    ActorValue,
    SPECIAL_INDICES,
)

if TYPE_CHECKING:
    from fnv_planner.gui.session import SessionManager
    from fnv_planner.gui.window import FnvPlannerWindow

_SPECIAL_ORDER: list[int] = [
    ActorValue.STRENGTH,
    ActorValue.PERCEPTION,
    ActorValue.ENDURANCE,
    ActorValue.CHARISMA,
    ActorValue.INTELLIGENCE,
    ActorValue.AGILITY,
    ActorValue.LUCK,
]


class SpecialGroup(Adw.PreferencesGroup):
    __gtype_name__ = "SpecialGroup"

    def __init__(
        self,
        session: SessionManager,
        window: FnvPlannerWindow,
    ) -> None:
        super().__init__(title="S.P.E.C.I.A.L.")
        self._session = session
        self._window = window
        self._updating = False

        # Budget label in the header suffix.
        self._budget_label = Gtk.Label()
        self._budget_label.add_css_class("dim-label")
        self.set_header_suffix(self._budget_label)

        # One SpinRow per SPECIAL attribute.
        self._spin_rows: dict[int, Adw.SpinRow] = {}
        for av in _SPECIAL_ORDER:
            name = ACTOR_VALUE_NAMES[av]
            adj = Gtk.Adjustment(
                value=session.special[av],
                lower=session.config.special_min,
                upper=session.config.special_max,
                step_increment=1,
                page_increment=1,
                page_size=0,
            )
            row = Adw.SpinRow(title=name, adjustment=adj)
            row.set_numeric(True)
            row.set_wrap(False)
            row.connect("notify::value", self._on_spin_changed, av)
            self.add(row)
            self._spin_rows[av] = row

        self._update_budget_label()
        self._clamp_uppers()

    def _on_spin_changed(self, row: Adw.SpinRow, _pspec: object, av: int) -> None:
        if self._updating:
            return
        value = int(row.get_value())
        if not self._session.set_special(av, value):
            # Revert the spin row to the session's value.
            self._updating = True
            row.set_value(self._session.special[av])
            self._updating = False
            return
        self._update_budget_label()
        self._clamp_uppers()
        self._window.emit("stats-changed")

    def _update_budget_label(self) -> None:
        remaining = self._session.special_remaining
        self._budget_label.set_label(f"Points remaining: {remaining}")

    def _clamp_uppers(self) -> None:
        """Adjust each spin row's upper bound so users can't overshoot the budget."""
        self._updating = True
        remaining = self._session.special_remaining
        for av, row in self._spin_rows.items():
            current = self._session.special[av]
            max_allowed = min(
                self._session.config.special_max,
                current + remaining,
            )
            row.get_adjustment().set_upper(max_allowed)
        self._updating = False
