"""Progression page view."""

from gi.repository import Gtk

from fnv_planner.models.constants import ACTOR_VALUE_NAMES
from fnv_planner.ui.controllers.progression_controller import ProgressionController


class ProgressionPage(Gtk.Box):
    """Progression timeline + delta inspector."""

    def __init__(self, controller: ProgressionController) -> None:
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        self._controller = controller
        self._updating = False
        self.set_hexpand(True)
        self.set_vexpand(True)
        self.set_margin_top(16)
        self.set_margin_bottom(16)
        self.set_margin_start(16)
        self.set_margin_end(16)

        title = Gtk.Label(label="Progression")
        title.add_css_class("title-2")
        title.set_xalign(0)
        self.append(title)

        self._status_label = Gtk.Label(xalign=0)
        self._status_label.add_css_class("error")
        self.append(self._status_label)

        progression_frame = Gtk.Frame(label="Timeline")
        progression_frame.set_hexpand(True)
        progression_frame.set_vexpand(True)
        self.append(progression_frame)
        progression_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        progression_box.set_margin_top(8)
        progression_box.set_margin_bottom(8)
        progression_box.set_margin_start(8)
        progression_box.set_margin_end(8)
        progression_frame.set_child(progression_box)
        self._books_summary_label = Gtk.Label(xalign=0)
        self._books_summary_label.set_wrap(True)
        progression_box.append(self._books_summary_label)
        progression_scroll = Gtk.ScrolledWindow()
        progression_scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        progression_scroll.set_vexpand(True)
        progression_box.append(progression_scroll)
        self._progression_list = Gtk.ListBox()
        self._progression_list.connect("row-selected", self._on_row_selected)
        progression_scroll.set_child(self._progression_list)

        anytime_frame = Gtk.Frame(label="Any-Time Perks (Not Scheduled In Timeline)")
        anytime_frame.set_hexpand(True)
        anytime_frame.set_vexpand(False)
        self.append(anytime_frame)
        anytime_scroll = Gtk.ScrolledWindow()
        anytime_scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        anytime_scroll.set_min_content_height(180)
        anytime_frame.set_child(anytime_scroll)
        self._anytime_list = Gtk.ListBox()
        anytime_scroll.set_child(self._anytime_list)

        self.refresh()

    def refresh(self) -> None:
        self._controller.refresh()
        self._updating = True
        try:
            # Progress tab now always shows full range to the current target level.
            self._controller.set_range(1, self._controller.target_level)
            self._render_anytime_perks()
            self._books_summary_label.set_text(self._controller.skill_books_summary())

            self._render_progression_rows()
        finally:
            self._updating = False

    def _render_progression_rows(self) -> None:
        self._clear_list(self._progression_list)
        rows = self._controller.progression_rows()
        active_level = self._controller.active_level
        prev_skills: dict[int, int] | None = None
        for snap in rows:
            if snap.level > 1:
                implants = self._controller.implants_between_levels_label(snap.level - 1, snap.level)
                if implants:
                    self._append_event_row(implants)
                between = self._controller.skill_books_between_levels_label(snap.level - 1, snap.level)
                if between:
                    self._append_event_row(between)

            perk_label = self._controller.perk_label_for_level(snap.level, snap.perk_id)
            allocation_label = self._controller.skill_allocation_label_for_level(snap.level)
            effective_skills = self._controller.effective_skills_for_level(snap.level, snap.stats.skills)

            row = Gtk.ListBoxRow()
            row.set_selectable(True)
            row.set_activatable(True)
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
            card.set_margin_top(6)
            card.set_margin_bottom(6)
            card.set_margin_start(8)
            card.set_margin_end(8)

            head = Gtk.Label(
                label=(
                    f"L{snap.level:>2}   Spent {snap.spent_skill_points:>2}   "
                    f"Unspent {snap.unspent_skill_points:>2}"
                ),
                xalign=0,
            )
            head.add_css_class("heading")
            card.append(head)

            perk_line = Gtk.Label(label=f"Perk: {perk_label}", xalign=0)
            perk_line.set_wrap(True)
            card.append(perk_line)
            perk_reason = self._controller.perk_reason_for_level(snap.level)
            if perk_reason:
                reason_line = Gtk.Label(label=f"Why: {perk_reason}", xalign=0)
                reason_line.set_wrap(True)
                card.append(reason_line)

            skills_line = Gtk.Label(label=f"Skill points: {allocation_label}", xalign=0)
            skills_line.set_wrap(True)
            card.append(skills_line)

            skills_markup = self._skills_absolute_markup(
                effective_skills,
                prev_skills,
            )
            absolute_skills = Gtk.Label(xalign=0)
            absolute_skills.set_use_markup(True)
            absolute_skills.set_wrap(True)
            absolute_skills.set_markup(f"Skills: {skills_markup}")
            skill_tooltips: list[str] = []
            for av in sorted(effective_skills):
                if av < 32 or av > 45:
                    continue
                desc = self._controller.actor_value_description(int(av))
                if not desc:
                    continue
                name = ACTOR_VALUE_NAMES.get(int(av), f"AV{av}")
                skill_tooltips.append(f"{name}: {desc}")
            absolute_skills.set_tooltip_text("\n".join(skill_tooltips) or None)
            card.append(absolute_skills)

            stats_line = Gtk.Label(
                label=(
                    f"Snapshot: HP {snap.stats.hit_points} | AP {snap.stats.action_points} | "
                    f"CW {snap.stats.carry_weight:.0f} | Crit {snap.stats.crit_chance:.0f}"
                ),
                xalign=0,
            )
            stats_line.set_wrap(True)
            stats_line.set_tooltip_text(self._controller.snapshot_stats_tooltip() or None)
            card.append(stats_line)

            row.set_child(card)
            row.set_tooltip_text(f"Level {snap.level}")
            self._progression_list.append(row)

            if active_level is not None and snap.level == active_level:
                self._progression_list.select_row(row)
            prev_skills = dict(effective_skills)

    def _append_event_row(self, text: str) -> None:
        event_row = Gtk.ListBoxRow()
        event_row.set_selectable(False)
        event_row.set_activatable(False)
        event_card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        event_card.set_margin_top(4)
        event_card.set_margin_bottom(4)
        event_card.set_margin_start(8)
        event_card.set_margin_end(8)
        event_line = Gtk.Label(label=text, xalign=0)
        event_line.set_wrap(True)
        event_card.append(event_line)
        event_row.set_child(event_card)
        self._progression_list.append(event_row)

    def _render_anytime_perks(self) -> None:
        self._clear_list(self._anytime_list)
        labels = self._controller.anytime_perk_labels or []
        if not labels:
            row = Gtk.ListBoxRow()
            row.set_child(Gtk.Label(label="None selected.", xalign=0))
            self._anytime_list.append(row)
            return
        for label in labels:
            row = Gtk.ListBoxRow()
            row.set_child(Gtk.Label(label=label, xalign=0, wrap=True))
            self._anytime_list.append(row)

    def _on_row_selected(self, _listbox: Gtk.ListBox, row: Gtk.ListBoxRow | None) -> None:
        if row is None or self._updating:
            return
        tooltip = row.get_tooltip_text() or ""
        if not tooltip.startswith("Level "):
            return
        level = int(tooltip.split(" ", 1)[1], 10)
        ok, message = self._controller.set_active_level(level)
        self._status_label.set_text("" if ok else (message or "Could not select level"))

    def _clear_list(self, listbox: Gtk.ListBox) -> None:
        child = listbox.get_first_child()
        while child is not None:
            next_child = child.get_next_sibling()
            listbox.remove(child)
            child = next_child

    def _skills_absolute_markup(
        self,
        current: dict[int, int],
        previous: dict[int, int] | None,
    ) -> str:
        parts: list[str] = []
        for av in sorted(current):
            if av < 32 or av > 45:
                continue
            name = ACTOR_VALUE_NAMES.get(av, f"AV{av}")
            value = int(current[av])
            changed = previous is not None and value != int(previous.get(av, value))
            token = f"{name} {value}"
            if changed:
                token = f"<b>{token}</b>"
            parts.append(token)
        return " | ".join(parts) if parts else "No skills"
