"""Main application window — two-pane layout with input controls and stats."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GObject, Gtk  # noqa: E402


class FnvPlannerWindow(Adw.ApplicationWindow):
    __gtype_name__ = "FnvPlannerWindow"

    __gsignals__ = {
        "stats-changed": (GObject.SignalFlags.RUN_FIRST, None, ()),
    }

    def __init__(self, **kwargs) -> None:  # noqa: ANN003
        super().__init__(**kwargs)
        self.set_title("FNV Character Planner")
        self.set_default_size(900, 700)

        app = self.get_application()
        session = app.session
        graph = app.graph

        # -- Header bar -------------------------------------------------------
        header = Adw.HeaderBar()

        # -- Left pane: input controls ----------------------------------------
        left_page = Adw.PreferencesPage()

        from fnv_planner.gui.widgets.name_sex import NameSexGroup
        from fnv_planner.gui.widgets.special import SpecialGroup
        from fnv_planner.gui.widgets.tags import TagsGroup
        from fnv_planner.gui.widgets.traits import TraitsGroup

        self._name_sex = NameSexGroup(session=session, window=self)
        left_page.add(self._name_sex)

        self._special = SpecialGroup(session=session, window=self)
        left_page.add(self._special)

        self._tags = TagsGroup(session=session, window=self)
        left_page.add(self._tags)

        self._traits = TraitsGroup(session=session, graph=graph, window=self)
        left_page.add(self._traits)

        left_scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            hexpand=True,
            vexpand=True,
        )
        left_scroll.set_child(left_page)

        # -- Right pane: derived stats ----------------------------------------
        from fnv_planner.gui.widgets.stats import StatsPanel

        self._stats = StatsPanel(session=session)

        right_scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            hexpand=True,
            vexpand=True,
        )
        right_scroll.set_child(self._stats)

        # -- Layout -----------------------------------------------------------
        panes = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        panes.append(left_scroll)

        sep = Gtk.Separator(orientation=Gtk.Orientation.VERTICAL)
        panes.append(sep)

        panes.append(right_scroll)

        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content.append(header)
        content.append(panes)

        self.set_content(content)

        # -- Signal wiring ----------------------------------------------------
        self.connect("stats-changed", self._on_stats_changed)

        # Initial stats refresh.
        self._on_stats_changed(self)

    def _on_stats_changed(self, _widget: GObject.Object) -> None:
        session = self.get_application().session
        stats = session.stats()
        self._stats.refresh(stats)
