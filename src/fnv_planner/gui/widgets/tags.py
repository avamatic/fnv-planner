"""Tag skill selection group — checkboxes for up to 3 tagged skills."""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from fnv_planner.models.constants import (  # noqa: E402
    ACTOR_VALUE_NAMES,
    SKILL_INDICES,
)

if TYPE_CHECKING:
    from fnv_planner.gui.session import SessionManager
    from fnv_planner.gui.window import FnvPlannerWindow


class TagsGroup(Adw.PreferencesGroup):
    __gtype_name__ = "TagsGroup"

    def __init__(
        self,
        session: SessionManager,
        window: FnvPlannerWindow,
    ) -> None:
        super().__init__(
            title="Tag Skills",
            description="Choose 3 tag skills (+15 bonus)",
        )
        self._session = session
        self._window = window
        self._updating = False
        self._checks: dict[int, Gtk.CheckButton] = {}

        # Sort skills by display name, skipping BIG_GUNS (33).
        skill_avs = sorted(
            (av for av in SKILL_INDICES if av in ACTOR_VALUE_NAMES and av != 33),
            key=lambda av: ACTOR_VALUE_NAMES[av],
        )

        for av in skill_avs:
            name = ACTOR_VALUE_NAMES[av]
            check = Gtk.CheckButton()
            check.set_active(av in session.tagged_skills)

            row = Adw.ActionRow(title=name)
            row.add_prefix(check)
            row.set_activatable_widget(check)

            check.connect("toggled", self._on_toggled, av)
            self.add(row)
            self._checks[av] = check

    def _on_toggled(self, button: Gtk.CheckButton, av: int) -> None:
        if self._updating:
            return
        if not self._session.toggle_tag(av):
            # Revert the check state.
            self._updating = True
            button.set_active(not button.get_active())
            self._updating = False
            return
        self._window.emit("stats-changed")
