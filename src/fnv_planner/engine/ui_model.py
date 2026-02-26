"""UI-facing adapter over BuildEngine for build/progression/library screens.

This module intentionally contains no GUI code. It provides stable, testable
data shapes that any UI toolkit can render.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from fnv_planner.engine.build_engine import BuildEngine
from fnv_planner.models.constants import ACTOR_VALUE_NAMES
from fnv_planner.models.derived_stats import CharacterStats
from fnv_planner.models.item import Armor, Weapon


EntityKind = Literal["special", "tag_skill", "trait", "perk", "equipment"]
CatalogKind = Literal["armor", "weapon"]


@dataclass(frozen=True, slots=True)
class SelectedEntity:
    """A currently selected build entity, with enough info to remove it."""

    kind: EntityKind
    label: str
    form_id: int | None = None
    actor_value: int | None = None
    level: int | None = None
    slot: int | None = None


@dataclass(frozen=True, slots=True)
class LevelSnapshot:
    """Single-level snapshot for progression views."""

    level: int
    perk_id: int | None
    spent_skill_points: int
    unspent_skill_points: int
    stats: CharacterStats


@dataclass(frozen=True, slots=True)
class LevelComparison:
    """Delta between two level snapshots."""

    from_level: int
    to_level: int
    stat_deltas: dict[str, float]
    skill_deltas: dict[int, int]


@dataclass(frozen=True, slots=True)
class CatalogItem:
    """Searchable gear catalog entry."""

    kind: CatalogKind
    form_id: int
    name: str
    slot: int
    value: int
    weight: float
    conditional_effects: int = 0
    excluded_conditional_effects: int = 0


@dataclass(frozen=True, slots=True)
class UiDiagnostic:
    """UI-facing warning/error message about uncertain or blocked context."""

    severity: Literal["info", "warning", "error"]
    code: str
    message: str
    level: int | None = None
    form_id: int | None = None


class BuildUiModel:
    """Read/write adapter for UI operations over a BuildEngine."""

    __slots__ = ("_engine", "_armors", "_weapons")

    def __init__(
        self,
        engine: BuildEngine,
        armors: dict[int, Armor] | None = None,
        weapons: dict[int, Weapon] | None = None,
    ) -> None:
        self._engine = engine
        self._armors = armors or {}
        self._weapons = weapons or {}

    def set_gear_catalog(
        self,
        armors: dict[int, Armor],
        weapons: dict[int, Weapon],
    ) -> None:
        self._armors = dict(armors)
        self._weapons = dict(weapons)

    def selected_entities(self) -> list[SelectedEntity]:
        """Return all currently selected entities in one flat list."""
        state = self._engine.state
        result: list[SelectedEntity] = []

        for av, val in sorted(state.special.items()):
            result.append(SelectedEntity(
                kind="special",
                actor_value=av,
                label=f"{ACTOR_VALUE_NAMES.get(av, f'AV{av}')}: {val}",
            ))

        for av in sorted(state.tagged_skills):
            result.append(SelectedEntity(
                kind="tag_skill",
                actor_value=av,
                label=f"Tag: {ACTOR_VALUE_NAMES.get(av, f'AV{av}')}",
            ))

        for trait_id in state.traits:
            result.append(SelectedEntity(
                kind="trait",
                form_id=trait_id,
                label=f"Trait {trait_id:#x}",
            ))

        for level in sorted(state.level_plans):
            perk_id = state.level_plans[level].perk
            if perk_id is None:
                continue
            result.append(SelectedEntity(
                kind="perk",
                form_id=perk_id,
                level=level,
                label=f"Level {level}: Perk {perk_id:#x}",
            ))

        for slot, form_id in sorted(state.equipment.items()):
            label = self._equipment_label(slot, form_id)
            result.append(SelectedEntity(
                kind="equipment",
                slot=slot,
                form_id=form_id,
                label=label,
            ))

        return result

    def search_selected_entities(self, query: str) -> list[SelectedEntity]:
        q = query.strip().lower()
        if not q:
            return self.selected_entities()
        return [e for e in self.selected_entities() if q in e.label.lower()]

    def remove_selected_entity(self, entity: SelectedEntity) -> bool:
        """Remove a selected entity in-place. Returns False if not removable."""
        if entity.kind == "tag_skill" and entity.actor_value is not None:
            state = self._engine.state
            if entity.actor_value not in state.tagged_skills:
                return False
            return self._engine.toggle_tagged_skill(entity.actor_value)

        if entity.kind == "trait" and entity.form_id is not None:
            return self._engine.toggle_trait(entity.form_id)

        if entity.kind == "perk" and entity.level is not None:
            self._engine.remove_perk(entity.level)
            return True

        if entity.kind == "equipment" and entity.slot is not None:
            self._engine.clear_equipment_slot(entity.slot)
            return True

        return False

    def level_snapshot(self, level: int) -> LevelSnapshot:
        plan = self._engine.state.level_plans.get(level)
        perk_id = plan.perk if plan is not None else None
        spent = sum(plan.skill_points.values()) if plan is not None else 0
        unspent = self._engine.unspent_skill_points_at(level) if level >= 2 else 0
        stats = self._engine.stats_at(level, self._armors, self._weapons)
        return LevelSnapshot(
            level=level,
            perk_id=perk_id,
            spent_skill_points=spent,
            unspent_skill_points=unspent,
            stats=stats,
        )

    def progression(self, from_level: int = 1, to_level: int | None = None) -> list[LevelSnapshot]:
        if to_level is None:
            to_level = self._engine.state.target_level
        if from_level < 1 or to_level < from_level:
            return []
        return [self.level_snapshot(level) for level in range(from_level, to_level + 1)]

    def compare_levels(self, from_level: int, to_level: int) -> LevelComparison:
        if to_level < from_level:
            raise ValueError("to_level must be >= from_level")
        before = self._engine.stats_at(from_level, self._armors, self._weapons)
        after = self._engine.stats_at(to_level, self._armors, self._weapons)

        stat_deltas = {
            "hit_points": float(after.hit_points - before.hit_points),
            "action_points": float(after.action_points - before.action_points),
            "carry_weight": after.carry_weight - before.carry_weight,
            "crit_chance": after.crit_chance - before.crit_chance,
            "crit_damage_potential": (
                after.crit_damage_potential - before.crit_damage_potential
            ),
            "melee_damage": after.melee_damage - before.melee_damage,
            "unarmed_damage": after.unarmed_damage - before.unarmed_damage,
            "poison_resistance": after.poison_resistance - before.poison_resistance,
            "rad_resistance": after.rad_resistance - before.rad_resistance,
            "skill_points_per_level": float(
                after.skill_points_per_level - before.skill_points_per_level
            ),
            "companion_nerve": after.companion_nerve - before.companion_nerve,
        }

        skill_deltas: dict[int, int] = {}
        for av, value in after.skills.items():
            prev = before.skills.get(av, 0)
            delta = value - prev
            if delta != 0:
                skill_deltas[av] = delta

        return LevelComparison(
            from_level=from_level,
            to_level=to_level,
            stat_deltas=stat_deltas,
            skill_deltas=skill_deltas,
        )

    def gear_catalog(self, query: str = "") -> list[CatalogItem]:
        q = query.strip().lower()
        items: list[CatalogItem] = []

        for armor in self._armors.values():
            if not armor.is_playable:
                continue
            item = CatalogItem(
                kind="armor",
                form_id=armor.form_id,
                name=armor.name,
                slot=armor.equipment_slot,
                value=armor.value,
                weight=armor.weight,
                conditional_effects=sum(1 for e in armor.stat_effects if e.is_conditional),
                excluded_conditional_effects=armor.conditional_effects_excluded,
            )
            if q and q not in item.name.lower():
                continue
            items.append(item)

        for weapon in self._weapons.values():
            if not weapon.is_playable:
                continue
            item = CatalogItem(
                kind="weapon",
                form_id=weapon.form_id,
                name=weapon.name,
                slot=weapon.equipment_slot,
                value=weapon.value,
                weight=weapon.weight,
                conditional_effects=sum(1 for e in weapon.stat_effects if e.is_conditional),
                excluded_conditional_effects=weapon.conditional_effects_excluded,
            )
            if q and q not in item.name.lower():
                continue
            items.append(item)

        return sorted(items, key=lambda it: (it.kind, it.name.lower()))

    def diagnostics(self, level: int | None = None) -> list[UiDiagnostic]:
        """Return warnings/errors for strict-mode uncertainty and exclusions."""
        if level is None:
            level = self._engine.state.target_level
        diagnostics: list[UiDiagnostic] = []

        # Selected perks that are blocked due to unknown raw conditions.
        state = self._engine.state
        for lv in sorted(state.level_plans):
            perk_id = state.level_plans[lv].perk
            if perk_id is None:
                continue
            unmet = self._engine.unmet_requirements_for_perk(perk_id, level=lv)
            if any("unsupported raw conditions" in msg for msg in unmet):
                diagnostics.append(UiDiagnostic(
                    severity="warning",
                    code="perk_raw_conditions_blocked",
                    message=(
                        f"Perk {perk_id:#x} at level {lv} is blocked by "
                        "unsupported raw CTDA conditions (strict mode)."
                    ),
                    level=lv,
                    form_id=perk_id,
                ))

        # Equipped items with conditional effects excluded in strict mode.
        for slot, form_id in sorted(state.equipment.items()):
            if form_id in self._armors:
                armor = self._armors[form_id]
                if armor.conditional_effects_excluded > 0:
                    diagnostics.append(UiDiagnostic(
                        severity="warning",
                        code="equipment_conditional_effects_excluded",
                        message=(
                            f"Equipped armor '{armor.name}' in slot {slot} has "
                            f"{armor.conditional_effects_excluded} conditional effect(s) "
                            "excluded by strict mode."
                        ),
                        form_id=form_id,
                    ))
            elif form_id in self._weapons:
                weapon = self._weapons[form_id]
                if weapon.conditional_effects_excluded > 0:
                    diagnostics.append(UiDiagnostic(
                        severity="warning",
                        code="equipment_conditional_effects_excluded",
                        message=(
                            f"Equipped weapon '{weapon.name}' in slot {slot} has "
                            f"{weapon.conditional_effects_excluded} conditional effect(s) "
                            "excluded by strict mode."
                        ),
                        form_id=form_id,
                    ))

        return diagnostics

    def _equipment_label(self, slot: int, form_id: int) -> str:
        if form_id in self._armors:
            return f"Slot {slot}: Armor {self._armors[form_id].name}"
        if form_id in self._weapons:
            return f"Slot {slot}: Weapon {self._weapons[form_id].name}"
        return f"Slot {slot}: Item {form_id:#x}"
