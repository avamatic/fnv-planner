"""Adw.Application subclass — owns engine state and creates the main window."""

from __future__ import annotations

import os
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio  # noqa: E402

from fnv_planner.graph.dependency_graph import DependencyGraph  # noqa: E402
from fnv_planner.gui.session import SessionManager  # noqa: E402
from fnv_planner.models.game_settings import GameSettings  # noqa: E402
from fnv_planner.models.perk import Perk  # noqa: E402


class FnvPlannerApp(Adw.Application):
    def __init__(self) -> None:
        super().__init__(
            application_id="com.github.fnv_planner",
            flags=Gio.ApplicationFlags.FLAGS_NONE,
        )
        self.session: SessionManager | None = None
        self.graph: DependencyGraph | None = None

    def do_activate(self) -> None:
        esm_path = os.environ.get("FNV_ESM_PATH")

        if esm_path:
            from fnv_planner.parser.perk_parser import parse_all_perks

            raw = Path(esm_path).read_bytes()
            gmst = GameSettings.from_esm(raw)
            perks: list[Perk] = parse_all_perks(raw)
        else:
            gmst = GameSettings.defaults()
            perks = []

        self.graph = DependencyGraph.build(perks)
        self.session = SessionManager(gmst, self.graph)

        from fnv_planner.gui.window import FnvPlannerWindow

        win = FnvPlannerWindow(application=self)
        win.present()
