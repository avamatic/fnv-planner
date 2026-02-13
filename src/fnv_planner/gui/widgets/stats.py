"""Derived stats display panel."""

from __future__ import annotations

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk  # noqa: E402

from fnv_planner.models.constants import ACTOR_VALUE_NAMES, SKILL_INDICES  # noqa: E402
from fnv_planner.models.derived_stats import CharacterStats  # noqa: E402


class StatsPanel(Adw.PreferencesPage):
    __gtype_name__ = "StatsPanel"

    def __init__(self, session: object) -> None:
        super().__init__()
        self._session = session
        self._rows: dict[str, Adw.ActionRow] = {}

        # -- Vitals -----------------------------------------------------------
        vitals = Adw.PreferencesGroup(title="Vitals")
        self._add_row(vitals, "hit_points", "Hit Points")
        self._add_row(vitals, "action_points", "Action Points")
        self._add_row(vitals, "carry_weight", "Carry Weight")
        self.add(vitals)

        # -- Combat -----------------------------------------------------------
        combat = Adw.PreferencesGroup(title="Combat")
        self._add_row(combat, "crit_chance", "Crit Chance")
        self._add_row(combat, "melee_damage", "Melee Damage")
        self._add_row(combat, "unarmed_damage", "Unarmed Damage")
        self.add(combat)

        # -- Resistances ------------------------------------------------------
        resist = Adw.PreferencesGroup(title="Resistances")
        self._add_row(resist, "poison_resistance", "Poison Resistance")
        self._add_row(resist, "rad_resistance", "Rad Resistance")
        self.add(resist)

        # -- Progression ------------------------------------------------------
        prog = Adw.PreferencesGroup(title="Progression")
        self._add_row(prog, "skill_points_per_level", "Skill Points / Level")
        self._add_row(prog, "companion_nerve", "Companion Nerve")
        self.add(prog)

        # -- Skills -----------------------------------------------------------
        skills_group = Adw.PreferencesGroup(title="Skills")
        # Sort skills by display name, skipping BIG_GUNS (33)
        skill_avs = sorted(
            (av for av in SKILL_INDICES if av in ACTOR_VALUE_NAMES and av != 33),
            key=lambda av: ACTOR_VALUE_NAMES[av],
        )
        for av in skill_avs:
            name = ACTOR_VALUE_NAMES[av]
            self._add_row(skills_group, f"skill_{av}", name)
        self.add(skills_group)

    def _add_row(self, group: Adw.PreferencesGroup, key: str, title: str) -> None:
        label = Gtk.Label(label="—")
        label.add_css_class("numeric")
        row = Adw.ActionRow(title=title)
        row.add_suffix(label)
        group.add(row)
        self._rows[key] = (row, label)

    def refresh(self, stats: CharacterStats) -> None:
        """Update all displayed values from a CharacterStats snapshot."""
        tagged = self._session.tagged_skills

        def _set(key: str, value: object, fmt: str = "") -> None:
            if key not in self._rows:
                return
            _row, label = self._rows[key]
            if isinstance(value, float):
                label.set_label(f"{value:{fmt}}" if fmt else f"{value:.1f}")
            else:
                label.set_label(str(value))

        _set("hit_points", stats.hit_points)
        _set("action_points", stats.action_points)
        _set("carry_weight", stats.carry_weight, ".0f")
        _set("crit_chance", stats.crit_chance, ".0f")
        _set("melee_damage", stats.melee_damage, ".1f")
        _set("unarmed_damage", stats.unarmed_damage, ".2f")
        _set("poison_resistance", stats.poison_resistance, ".0f")
        _set("rad_resistance", stats.rad_resistance, ".0f")
        _set("skill_points_per_level", stats.skill_points_per_level)
        _set("companion_nerve", stats.companion_nerve, ".0f")

        for av in SKILL_INDICES:
            if av == 33 or av not in ACTOR_VALUE_NAMES:
                continue
            key = f"skill_{av}"
            value = stats.skills.get(av, 0)
            if key in self._rows:
                _row, label = self._rows[key]
                tag_marker = "  [TAG]" if av in tagged else ""
                label.set_label(f"{value}{tag_marker}")
