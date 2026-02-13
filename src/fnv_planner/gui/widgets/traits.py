"""Trait selection group — checkboxes for up to 2 traits."""

from __future__ import annotations

from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from fnv_planner.graph.dependency_graph import DependencyGraph  # noqa: E402

if TYPE_CHECKING:
    from fnv_planner.gui.session import SessionManager
    from fnv_planner.gui.window import FnvPlannerWindow


class TraitsGroup(Adw.PreferencesGroup):
    __gtype_name__ = "TraitsGroup"

    def __init__(
        self,
        session: SessionManager,
        graph: DependencyGraph,
        window: FnvPlannerWindow,
    ) -> None:
        super().__init__(
            title="Traits",
            description="Choose up to 2 traits",
        )
        self._session = session
        self._graph = graph
        self._window = window
        self._updating = False
        self._checks: dict[int, Gtk.CheckButton] = {}

        trait_ids = graph.available_traits()

        if not trait_ids:
            row = Adw.ActionRow(
                title="No traits available",
                subtitle="Load an ESM to enable traits",
            )
            self.add(row)
            return

        # Sort traits by name.
        trait_nodes = []
        for tid in trait_ids:
            node = graph.get_node(tid)
            if node is not None:
                trait_nodes.append(node)
        trait_nodes.sort(key=lambda n: n.name)

        for node in trait_nodes:
            check = Gtk.CheckButton()
            check.set_active(node.perk_id in session.traits)

            row = Adw.ActionRow(
                title=node.name,
                subtitle=self._get_trait_description(node.perk_id),
            )
            row.add_prefix(check)
            row.set_activatable_widget(check)

            check.connect("toggled", self._on_toggled, node.perk_id)
            self.add(row)
            self._checks[node.perk_id] = check

    def _get_trait_description(self, perk_id: int) -> str:
        """Get the trait description from the perk parser data if available."""
        # The dependency graph stores PerkNode, which doesn't carry
        # the full description. We show the editor_id as a fallback.
        node = self._graph.get_node(perk_id)
        if node is not None:
            return node.editor_id
        return ""

    def _on_toggled(self, button: Gtk.CheckButton, perk_id: int) -> None:
        if self._updating:
            return
        if not self._session.toggle_trait(perk_id):
            self._updating = True
            button.set_active(not button.get_active())
            self._updating = False
            return
        self._window.emit("stats-changed")
