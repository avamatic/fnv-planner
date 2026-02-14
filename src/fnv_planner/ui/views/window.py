"""Main application window."""

from gi.repository import Adw, Gtk

from fnv_planner.ui.controllers.build_controller import BuildController
from fnv_planner.ui.controllers.graph_controller import GraphController
from fnv_planner.ui.controllers.library_controller import LibraryController
from fnv_planner.ui.controllers.progression_controller import ProgressionController
from fnv_planner.ui.bootstrap import BuildSession
from fnv_planner.ui.state import UiState
from fnv_planner.ui.views.build_page import BuildPage
from fnv_planner.ui.views.graph_page import GraphPage
from fnv_planner.ui.views.library_page import LibraryPage
from fnv_planner.ui.views.progression_page import ProgressionPage


class MainWindow(Adw.ApplicationWindow):
    """Top-level window with tabbed navigation."""

    def __init__(self, app: Adw.Application, state: UiState, session: BuildSession) -> None:
        super().__init__(application=app, title="FNV Planner")
        self._state = state
        self._session = session
        self._detached_windows: list[Adw.ApplicationWindow] = []

        self._build_controller = BuildController(
            engine=session.engine,
            ui_model=session.ui_model,
            perks=session.perks,
            challenge_perk_ids=session.challenge_perk_ids,
            skill_books_by_av=session.skill_books_by_av,
            linked_spell_names_by_form=session.linked_spell_names_by_form,
            linked_spell_stat_bonuses_by_form=session.linked_spell_stat_bonuses_by_form,
            state=state,
            av_descriptions_by_av=session.av_descriptions_by_av,
            current_level=1,
        )
        self._progression_controller = ProgressionController(
            engine=session.engine,
            ui_model=session.ui_model,
            perks=session.perks,
            state=state,
            av_descriptions_by_av=session.av_descriptions_by_av,
        )
        self._library_controller = LibraryController(
            engine=session.engine,
            ui_model=session.ui_model,
            armors=session.armors,
            weapons=session.weapons,
            state=state,
        )
        self._graph_controller = GraphController(state=state)

        self.set_default_size(1440, 900)
        self.set_size_request(1100, 700)

        toolbar_view = Adw.ToolbarView()
        self.set_content(toolbar_view)

        header = Adw.HeaderBar()
        toolbar_view.add_top_bar(header)

        self._title_label = Gtk.Label()
        self._title_label.add_css_class("title-4")
        self._sync_title()
        header.set_title_widget(self._title_label)

        tabs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        tabs_box.set_hexpand(True)
        tabs_box.set_vexpand(True)
        toolbar_view.set_content(tabs_box)

        tab_view = Adw.TabView()
        tab_view.connect("create-window", self._on_create_window)
        tab_view.set_hexpand(True)
        tab_view.set_vexpand(True)
        tab_bar = Adw.TabBar.new()
        tab_bar.set_view(tab_view)
        tabs_box.append(tab_bar)
        tabs_box.append(tab_view)

        self._build_page = BuildPage(self._build_controller)
        self._progression_controller.set_anytime_perks(
            self._build_controller.anytime_desired_perk_labels()
        )
        self._progression_controller.set_perk_reasons(self._build_controller.perk_reasons())
        self._progression_controller.set_skill_book_usage(
            self._build_controller.needed_skill_books(),
            self._build_controller.total_skill_books(),
            self._build_controller.skill_book_rows(),
            self._build_controller.skill_book_usage_by_level(),
            self._build_controller.skill_book_points_by_level(),
        )
        self._progression_controller.set_zero_cost_perks_by_level(
            self._build_controller.zero_cost_perk_events_by_level()
        )
        self._progression_controller.set_implant_usage_by_level(
            self._build_controller.implant_points_by_level()
        )
        self._progression_controller.set_flat_skill_bonus_by_level(
            self._build_controller.flat_skill_bonuses_by_level()
        )
        self._progression_page = ProgressionPage(self._progression_controller)
        self._library_page = LibraryPage(self._library_controller)

        self._build_controller.on_change = self._on_build_changed
        self._library_controller.on_change = self._on_build_changed

        self._add_page(tab_view, "Build", self._build_page)
        self._add_page(tab_view, "Progression", self._progression_page)
        self._add_page(tab_view, "Library", self._library_page)
        self._add_page(tab_view, "Cool Stuff", GraphPage())

    def _sync_title(self) -> None:
        self._title_label.set_label(
            f"{self._state.build_name}  -  Target L{self._state.target_level}"
        )

    def _add_page(self, tab_view: Adw.TabView, title: str, child: Gtk.Widget) -> None:
        page = tab_view.append(child)
        page.set_title(title)

    def _on_create_window(self, _tab_view: Adw.TabView) -> Adw.TabView:
        app = self.get_application()
        detached = Adw.ApplicationWindow(application=app, title="FNV Planner")
        detached.set_default_size(1100, 700)

        toolbar_view = Adw.ToolbarView()
        detached.set_content(toolbar_view)
        toolbar_view.add_top_bar(Adw.HeaderBar())

        tabs_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        tabs_box.set_hexpand(True)
        tabs_box.set_vexpand(True)
        toolbar_view.set_content(tabs_box)

        tab_view = Adw.TabView()
        tab_view.connect("create-window", self._on_create_window)
        tab_view.set_hexpand(True)
        tab_view.set_vexpand(True)
        tab_bar = Adw.TabBar.new()
        tab_bar.set_view(tab_view)
        tabs_box.append(tab_bar)
        tabs_box.append(tab_view)

        self._detached_windows.append(detached)
        detached.present()
        return tab_view

    def _on_build_changed(self) -> None:
        self._sync_title()
        self._progression_controller.set_anytime_perks(
            self._build_controller.anytime_desired_perk_labels()
        )
        self._progression_controller.set_perk_reasons(self._build_controller.perk_reasons())
        self._progression_controller.set_skill_book_usage(
            self._build_controller.needed_skill_books(),
            self._build_controller.total_skill_books(),
            self._build_controller.skill_book_rows(),
            self._build_controller.skill_book_usage_by_level(),
            self._build_controller.skill_book_points_by_level(),
        )
        self._progression_controller.set_zero_cost_perks_by_level(
            self._build_controller.zero_cost_perk_events_by_level()
        )
        self._progression_controller.set_implant_usage_by_level(
            self._build_controller.implant_points_by_level()
        )
        self._progression_controller.set_flat_skill_bonus_by_level(
            self._build_controller.flat_skill_bonuses_by_level()
        )
        self._build_page.refresh()
        self._progression_page.refresh()
        self._library_page.refresh()
