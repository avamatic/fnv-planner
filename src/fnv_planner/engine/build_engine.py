"""Build engine — validates and simulates character builds level-by-level.

Orchestrates Character, compute_stats(), and DependencyGraph to answer
questions like "how many skill points do I have at level 8?" and "which
perks can I take at level 12?"

The engine tracks per-level allocations via LevelPlan, accumulates them
into a Character snapshot via materialize(), and caches CharacterStats
to avoid redundant computation during validation.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

from fnv_planner.engine.build_config import BuildConfig
from fnv_planner.graph.dependency_graph import DependencyGraph
from fnv_planner.models.character import Character
from fnv_planner.models.constants import (
    SKILL_GOVERNING_ATTRIBUTE,
    SPECIAL_INDICES,
    ActorValue,
)
from fnv_planner.models.derived_stats import (
    CharacterStats,
    DerivedStats,
    compute_stats,
)
from fnv_planner.models.game_settings import GameSettings
from fnv_planner.models.item import Armor, Weapon

# Base valid skill AV indices (without optional Big Guns support).
_BASE_VALID_SKILLS = frozenset(SKILL_GOVERNING_ATTRIBUTE.keys())


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class LevelPlan:
    """Per-level allocation: skill points spent THIS level + optional perk."""

    level: int
    skill_points: dict[int, int] = field(default_factory=dict)
    perk: int | None = None


@dataclass(slots=True)
class BuildState:
    """Serialisable snapshot of all build choices (creation + level-ups)."""

    name: str = "Courier"
    sex: int | None = None
    special: dict[int, int] = field(default_factory=dict)
    tagged_skills: set[int] = field(default_factory=set)
    traits: list[int] = field(default_factory=list)
    equipment: dict[int, int] = field(default_factory=dict)
    level_plans: dict[int, LevelPlan] = field(default_factory=dict)
    target_level: int = 1


@dataclass(slots=True)
class BuildError:
    """A single rule violation discovered during validation."""

    level: int         # 0 = creation phase
    category: str      # "special" | "tags" | "traits" | "skill_points" | "perk" | "skill_cap"
    message: str


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class BuildEngine:
    """Validates and simulates a character build level-by-level.

    Consumes GameSettings, DependencyGraph, and BuildConfig without
    modifying any of them. Internally maintains a BuildState and a
    CharacterStats cache that is invalidated on mutation.
    """

    __slots__ = ("_state", "_gmst", "_graph", "_config", "_derived", "_stats_cache")

    def __init__(
        self,
        gmst: GameSettings,
        graph: DependencyGraph,
        config: BuildConfig | None = None,
    ) -> None:
        self._gmst = gmst
        self._graph = graph
        self._config = config or BuildConfig()
        self._derived = DerivedStats(gmst)
        self._state = BuildState()
        self._stats_cache: dict[int, CharacterStats] = {}

    # --- Factories ---------------------------------------------------------

    @classmethod
    def new_build(
        cls,
        gmst: GameSettings,
        graph: DependencyGraph,
        config: BuildConfig | None = None,
    ) -> BuildEngine:
        """Create a fresh build engine with default state."""
        return cls(gmst, graph, config)

    @classmethod
    def from_state(
        cls,
        state: BuildState,
        gmst: GameSettings,
        graph: DependencyGraph,
        config: BuildConfig | None = None,
    ) -> BuildEngine:
        """Restore an engine from a previously saved BuildState."""
        engine = cls(gmst, graph, config)
        engine._state = copy.deepcopy(state)
        return engine

    def copy(self) -> BuildEngine:
        """Deep-copy the engine for speculative exploration."""
        clone = BuildEngine.__new__(BuildEngine)
        clone._gmst = self._gmst
        clone._graph = self._graph
        clone._config = self._config
        clone._derived = self._derived
        clone._state = copy.deepcopy(self._state)
        clone._stats_cache = {}
        return clone

    # --- State property ----------------------------------------------------

    @property
    def state(self) -> BuildState:
        """Return a deep copy of the current build state for serialisation."""
        return copy.deepcopy(self._state)

    @property
    def max_level(self) -> int:
        """Maximum character level from GMST."""
        return self._derived.max_level()

    # --- Cache helpers -----------------------------------------------------

    def _invalidate_from(self, level: int) -> None:
        """Clear cached stats from *level* upward."""
        to_remove = [lv for lv in self._stats_cache if lv >= level]
        for lv in to_remove:
            del self._stats_cache[lv]

    def _valid_skills(self) -> frozenset[int]:
        if self._config.include_big_guns:
            return _BASE_VALID_SKILLS | {int(ActorValue.BIG_GUNS)}
        return _BASE_VALID_SKILLS

    def _compute_stats(
        self,
        char: Character,
        armors: dict[int, Armor] | None = None,
        weapons: dict[int, Weapon] | None = None,
    ) -> CharacterStats:
        return compute_stats(
            char,
            self._gmst,
            armors,
            weapons,
            include_big_guns=self._config.include_big_guns,
            big_guns_governing_attribute=self._config.big_guns_governing_attribute,
        )

    # --- Creation phase ----------------------------------------------------

    def set_name(self, name: str) -> None:
        self._state.name = name

    def set_sex(self, sex: int) -> None:
        """Set character sex (0=Male, 1=Female)."""
        if sex not in (0, 1):
            raise ValueError(f"sex must be 0 (Male) or 1 (Female), got {sex}")
        self._state.sex = sex
        self._invalidate_from(1)

    def set_special(self, special: dict[int, int]) -> None:
        """Set SPECIAL allocation. Validates budget, range, and keys."""
        self._validate_special_map(special)
        total = sum(special.values())
        if total != self._config.special_budget:
            raise ValueError(
                f"SPECIAL budget must be {self._config.special_budget}, got {total}"
            )
        self._state.special = dict(special)
        self._invalidate_from(1)

    def set_special_working(self, special: dict[int, int]) -> None:
        """Set SPECIAL allocation for incremental UIs.

        Validates key/range constraints and enforces total <= budget.
        """
        self._validate_special_map(special)
        total = sum(special.values())
        if total > self._config.special_budget:
            raise ValueError(
                f"SPECIAL budget exceeded: {total} > {self._config.special_budget}"
            )
        self._state.special = dict(special)
        self._invalidate_from(1)

    def _validate_special_map(self, special: dict[int, int]) -> None:
        """Validate SPECIAL keys and per-stat range."""
        cfg = self._config
        if set(special.keys()) != SPECIAL_INDICES:
            raise ValueError(
                f"Must provide exactly the 7 SPECIAL stats "
                f"(AV indices {sorted(SPECIAL_INDICES)}), "
                f"got {sorted(special.keys())}"
            )
        for av, val in special.items():
            if val < cfg.special_min or val > cfg.special_max:
                raise ValueError(
                    f"SPECIAL stat {av} = {val} is out of range "
                    f"[{cfg.special_min}, {cfg.special_max}]"
                )

    def set_tagged_skills(self, skills: set[int]) -> None:
        """Set tagged skills. Validates count and AV indices."""
        cfg = self._config
        if len(skills) != cfg.num_tagged_skills:
            raise ValueError(
                f"Must tag exactly {cfg.num_tagged_skills} skills, got {len(skills)}"
            )
        for av in skills:
            if av not in self._valid_skills():
                raise ValueError(f"Invalid skill AV index: {av}")
        self._state.tagged_skills = set(skills)
        self._invalidate_from(1)

    def toggle_tagged_skill(self, av: int) -> bool:
        """Toggle one tagged skill. Returns True if the toggle was applied."""
        if av not in self._valid_skills():
            return False
        tags = self._state.tagged_skills
        if av in tags:
            tags.discard(av)
            self._invalidate_from(1)
            return True
        if len(tags) >= self._config.num_tagged_skills:
            return False
        tags.add(av)
        self._invalidate_from(1)
        return True

    def set_traits(self, traits: list[int]) -> None:
        """Set traits (0 to max_traits). Must be available in the graph."""
        cfg = self._config
        if len(traits) > cfg.max_traits:
            raise ValueError(
                f"At most {cfg.max_traits} traits allowed, got {len(traits)}"
            )
        if len(traits) != len(set(traits)):
            raise ValueError("Duplicate traits are not allowed")
        available = set(self._graph.available_traits())
        for t in traits:
            if t not in available:
                raise ValueError(f"Trait {t:#x} is not available")
        self._state.traits = list(traits)
        self._invalidate_from(1)

    def toggle_trait(self, trait_id: int) -> bool:
        """Toggle one trait. Returns True if the toggle was applied."""
        traits = self._state.traits
        if trait_id in traits:
            traits.remove(trait_id)
            self._invalidate_from(1)
            return True
        available = set(self._graph.available_traits())
        if trait_id not in available:
            return False
        if len(traits) >= self._config.max_traits:
            return False
        traits.append(trait_id)
        self._invalidate_from(1)
        return True

    def set_equipment(self, slot: int, item_form_id: int) -> None:
        """Equip an item form ID into a slot index."""
        self._state.equipment[slot] = item_form_id
        self._invalidate_from(1)

    def set_equipment_bulk(self, equipment: dict[int, int]) -> None:
        """Replace all equipped items in one atomic update.

        Useful for UI flows that apply multiple slot changes at once and want
        a single cache invalidation.
        """
        self._state.equipment = dict(equipment)
        self._invalidate_from(1)

    def clear_equipment_slot(self, slot: int) -> None:
        """Unequip whatever is currently in *slot*."""
        self._state.equipment.pop(slot, None)
        self._invalidate_from(1)

    # --- Target level ------------------------------------------------------

    def set_target_level(self, level: int) -> None:
        """Set the build's target level, creating/removing LevelPlans."""
        if level < 1 or level > self.max_level:
            raise ValueError(
                f"Target level must be 1..{self.max_level}, got {level}"
            )
        old_target = self._state.target_level
        self._state.target_level = level

        # Create empty plans for new levels.
        for lv in range(2, level + 1):
            if lv not in self._state.level_plans:
                self._state.level_plans[lv] = LevelPlan(level=lv)

        # Remove plans beyond the new target.
        to_remove = [lv for lv in self._state.level_plans if lv > level]
        for lv in to_remove:
            del self._state.level_plans[lv]

        if level < old_target:
            self._invalidate_from(level + 1)

    # --- Level-up phase ----------------------------------------------------

    def allocate_skill_points(self, level: int, points: dict[int, int]) -> None:
        """Set skill point allocation for a single level.

        *points* maps skill AV index to points spent THIS level.
        Replaces any previous allocation at this level.
        """
        if level < 2 or level > self._state.target_level:
            raise ValueError(
                f"Cannot allocate at level {level} "
                f"(target is {self._state.target_level})"
            )
        plan = self._state.level_plans.get(level)
        if plan is None:
            raise ValueError(f"No LevelPlan for level {level}")

        # Validate skill indices.
        for av in points:
            if av not in self._valid_skills():
                raise ValueError(f"Invalid skill AV index: {av}")

        # Validate individual point values are positive.
        for av, pts in points.items():
            if pts < 0:
                raise ValueError(
                    f"Negative skill points ({pts}) for AV {av}"
                )

        # Validate budget: skill points earned at this level.
        budget = self._skill_budget_at(level)
        spent = sum(points.values())
        if spent > budget:
            raise ValueError(
                f"Level {level}: spending {spent} points but budget is {budget}"
            )

        # Validate skill cap (base skill, before equipment).
        # Accumulate points from levels 2..level-1, then add this level's.
        cumulative = self._cumulative_skill_points(level - 1)
        for av, pts in points.items():
            existing = cumulative.get(av, 0)
            base_skill = self._base_skill(av, existing + pts)
            if base_skill > self._config.skill_cap:
                raise ValueError(
                    f"Skill AV {av} would reach {base_skill}, "
                    f"exceeding cap of {self._config.skill_cap}"
                )

        plan.skill_points = dict(points)
        self._invalidate_from(level)

    def select_perk(self, level: int, perk_id: int) -> None:
        """Select a perk at the given level."""
        if level < 2 or level > self._state.target_level:
            raise ValueError(
                f"Cannot select perk at level {level} "
                f"(target is {self._state.target_level})"
            )
        if not self.is_perk_level(level):
            raise ValueError(f"Level {level} does not award a perk")
        plan = self._state.level_plans.get(level)
        if plan is None:
            raise ValueError(f"No LevelPlan for level {level}")

        # Build a character snapshot excluding this level's current perk,
        # so can_take_perk doesn't see a stale selection as "already taken".
        char = self._materialize_for_perk_check(level)
        stats = self._compute_stats(char)
        if not self._graph.can_take_perk(perk_id, char, stats):
            raise ValueError(
                f"Perk {perk_id:#x} is not available at level {level}"
            )

        plan.perk = perk_id
        self._invalidate_from(level)

    def remove_perk(self, level: int) -> None:
        """Clear the perk selection at a level."""
        plan = self._state.level_plans.get(level)
        if plan is None:
            raise ValueError(f"No LevelPlan for level {level}")
        plan.perk = None
        self._invalidate_from(level)

    # --- Queries -----------------------------------------------------------

    def materialize(
        self,
        level: int | None = None,
        armors: dict[int, Armor] | None = None,
        weapons: dict[int, Weapon] | None = None,
    ) -> Character:
        """Accumulate build plans into a Character snapshot at *level*.

        If *level* is None, uses the target level.
        """
        if level is None:
            level = self._state.target_level

        # Accumulate skill points spent across all levels up to *level*.
        cumulative = self._cumulative_skill_points(level)

        # Accumulate perks across all levels up to *level*.
        perks: dict[int, list[int]] = {}
        for lv in range(2, level + 1):
            plan = self._state.level_plans.get(lv)
            if plan and plan.perk is not None:
                perks.setdefault(lv, []).append(plan.perk)

        equipment = dict(self._state.equipment)

        return Character(
            name=self._state.name,
            level=level,
            sex=self._state.sex,
            special=dict(self._state.special) if self._state.special else {},
            tagged_skills=set(self._state.tagged_skills),
            skill_points_spent=cumulative,
            traits=list(self._state.traits),
            perks=perks,
            equipment=equipment,
        )

    def stats_at(
        self,
        level: int | None = None,
        armors: dict[int, Armor] | None = None,
        weapons: dict[int, Weapon] | None = None,
    ) -> CharacterStats:
        """Compute CharacterStats at a given level (cached when no equipment)."""
        if level is None:
            level = self._state.target_level

        # Use cache only when no equipment is provided.
        if armors is None and weapons is None and level in self._stats_cache:
            return self._stats_cache[level]

        char = self.materialize(level, armors, weapons)
        stats = self._compute_stats(char, armors, weapons)

        if armors is None and weapons is None:
            self._stats_cache[level] = stats

        return stats

    def available_perks_at(self, level: int) -> list[int]:
        """Return perk IDs available at *level* given the current build."""
        char = self.materialize(level)
        stats = self._compute_stats(char)
        return self._graph.available_perks(char, stats)

    def unmet_requirements_for_perk(
        self,
        perk_id: int,
        level: int | None = None,
    ) -> list[str]:
        """Return unmet requirement descriptions for a perk at a given level."""
        if level is None:
            level = self._state.target_level
        char = self.materialize(level)
        stats = self._compute_stats(char)
        return self._graph.unmet_requirements(perk_id, char, stats)

    def unspent_skill_points_at(self, level: int) -> int:
        """Return unspent skill points at a given level."""
        budget = self._skill_budget_at(level)
        plan = self._state.level_plans.get(level)
        spent = sum(plan.skill_points.values()) if plan else 0
        return budget - spent

    def total_skill_budget(self, up_to_level: int | None = None) -> int:
        """Cumulative skill points earned across all levels up to *up_to_level*."""
        if up_to_level is None:
            up_to_level = self._state.target_level
        total = 0
        for lv in range(2, up_to_level + 1):
            total += self._skill_budget_at(lv)
        return total

    def total_skill_points_spent(self, up_to_level: int | None = None) -> int:
        """Cumulative skill points spent across all levels."""
        if up_to_level is None:
            up_to_level = self._state.target_level
        total = 0
        for lv in range(2, up_to_level + 1):
            plan = self._state.level_plans.get(lv)
            if plan:
                total += sum(plan.skill_points.values())
        return total

    def is_perk_level(self, level: int) -> bool:
        """True if *level* awards a perk."""
        return level >= 2 and level % self._config.perk_every_n_levels == 0

    def perk_levels(self, up_to: int | None = None) -> list[int]:
        """Return sorted list of perk-awarding levels up to *up_to*."""
        if up_to is None:
            up_to = self._state.target_level
        return [lv for lv in range(2, up_to + 1) if self.is_perk_level(lv)]

    # --- Validation --------------------------------------------------------

    def validate(self) -> list[BuildError]:
        """Check the entire build for rule violations."""
        errors = self.validate_creation()
        for lv in range(2, self._state.target_level + 1):
            errors.extend(self.validate_level(lv))
        return errors

    def validate_creation(self) -> list[BuildError]:
        """Validate creation-phase choices."""
        errors: list[BuildError] = []
        cfg = self._config

        # SPECIAL
        if not self._state.special:
            errors.append(BuildError(0, "special", "SPECIAL not set"))
        else:
            if set(self._state.special.keys()) != SPECIAL_INDICES:
                errors.append(BuildError(
                    0, "special",
                    f"Must provide all 7 SPECIAL stats, "
                    f"got {sorted(self._state.special.keys())}",
                ))
            else:
                for av, val in self._state.special.items():
                    if val < cfg.special_min or val > cfg.special_max:
                        errors.append(BuildError(
                            0, "special",
                            f"SPECIAL {av} = {val} out of range "
                            f"[{cfg.special_min}, {cfg.special_max}]",
                        ))
                total = sum(self._state.special.values())
                if total != cfg.special_budget:
                    errors.append(BuildError(
                        0, "special",
                        f"SPECIAL budget is {cfg.special_budget}, got {total}",
                    ))

        # Tagged skills
        if len(self._state.tagged_skills) != cfg.num_tagged_skills:
            errors.append(BuildError(
                0, "tags",
                f"Must tag {cfg.num_tagged_skills} skills, "
                f"have {len(self._state.tagged_skills)}",
            ))
        for av in self._state.tagged_skills:
            if av not in self._valid_skills():
                errors.append(BuildError(
                    0, "tags", f"Invalid tagged skill AV index: {av}"
                ))

        # Traits
        if len(self._state.traits) > cfg.max_traits:
            errors.append(BuildError(
                0, "traits",
                f"At most {cfg.max_traits} traits, have {len(self._state.traits)}",
            ))
        if len(self._state.traits) != len(set(self._state.traits)):
            errors.append(BuildError(0, "traits", "Duplicate traits"))
        available_traits = set(self._graph.available_traits())
        for t in self._state.traits:
            if t not in available_traits:
                errors.append(BuildError(
                    0, "traits", f"Trait {t:#x} is not available"
                ))

        return errors

    def validate_level(self, level: int) -> list[BuildError]:
        """Validate a single level's plan."""
        errors: list[BuildError] = []
        plan = self._state.level_plans.get(level)

        if plan is None:
            errors.append(BuildError(
                level, "skill_points", f"No LevelPlan for level {level}"
            ))
            return errors

        # Skill point budget
        budget = self._skill_budget_at(level)
        spent = sum(plan.skill_points.values())
        if spent > budget:
            errors.append(BuildError(
                level, "skill_points",
                f"Spent {spent} points but budget is {budget}",
            ))

        # Validate skill AV indices
        for av in plan.skill_points:
            if av not in self._valid_skills():
                errors.append(BuildError(
                    level, "skill_points",
                    f"Invalid skill AV index: {av}",
                ))

        # Skill cap check
        cumulative = self._cumulative_skill_points(level)
        for av, total_pts in cumulative.items():
            base = self._base_skill(av, total_pts)
            if base > self._config.skill_cap:
                errors.append(BuildError(
                    level, "skill_cap",
                    f"Skill AV {av} base value {base} exceeds cap {self._config.skill_cap}",
                ))

        # Perk validation — materialize WITHOUT this level's perk to avoid
        # the max-rank false positive (the perk is already in the snapshot).
        if self.is_perk_level(level) and plan.perk is not None:
            char = self._materialize_for_perk_check(level)
            stats = self._compute_stats(char)
            if not self._graph.can_take_perk(plan.perk, char, stats):
                errors.append(BuildError(
                    level, "perk",
                    f"Perk {plan.perk:#x} is not available at level {level}",
                ))
        elif not self.is_perk_level(level) and plan.perk is not None:
            errors.append(BuildError(
                level, "perk",
                f"Level {level} does not award a perk",
            ))

        return errors

    def is_valid(self) -> bool:
        """True if the entire build has no rule violations."""
        return len(self.validate()) == 0

    def is_complete(self) -> bool:
        """True if all points spent, all perk slots filled, up to target level."""
        # Must have valid creation phase.
        if self.validate_creation():
            return False

        for lv in range(2, self._state.target_level + 1):
            plan = self._state.level_plans.get(lv)
            if plan is None:
                return False

            # All skill points must be spent.
            budget = self._skill_budget_at(lv)
            spent = sum(plan.skill_points.values())
            if spent != budget:
                return False

            # All perk levels must have a perk selected.
            if self.is_perk_level(lv) and plan.perk is None:
                return False

        return True

    # --- Internal helpers --------------------------------------------------

    def _skill_budget_at(self, level: int) -> int:
        """Skill points earned at a specific level.

        Based on Intelligence at level-1 (the character's stats when
        they level up from level-1 to level).
        """
        if level < 2:
            return 0
        # Get stats at the previous level to determine INT-based budget.
        prev_stats = self.stats_at(level - 1)
        return prev_stats.skill_points_per_level

    def _cumulative_skill_points(self, up_to_level: int) -> dict[int, int]:
        """Accumulate skill point allocations from level 2 up to *up_to_level*."""
        cumulative: dict[int, int] = {}
        for lv in range(2, up_to_level + 1):
            plan = self._state.level_plans.get(lv)
            if plan:
                for av, pts in plan.skill_points.items():
                    cumulative[av] = cumulative.get(av, 0) + pts
        return cumulative

    def _base_skill(self, av: int, points_spent: int) -> int:
        """Compute base skill value (no equipment) for a skill AV index."""
        if av in SKILL_GOVERNING_ATTRIBUTE:
            gov_av = SKILL_GOVERNING_ATTRIBUTE[av]
        elif av == int(ActorValue.BIG_GUNS) and self._config.include_big_guns:
            gov_av = self._config.big_guns_governing_attribute
        else:
            raise ValueError(f"Invalid skill AV index: {av}")
        special = self._state.special or {}
        gov_val = special.get(gov_av, 5)
        luck = special.get(11, 5)  # ActorValue.LUCK = 11
        base = self._derived.initial_skill(gov_val, luck)
        if av in self._state.tagged_skills:
            base += self._derived.tag_bonus()
        base += points_spent
        return base

    def _materialize_for_perk_check(self, level: int) -> Character:
        """Like materialize() but excludes the perk at *level*.

        Used by validate_level() to avoid the max-rank false positive:
        if the perk is already in the snapshot, can_take_perk() would
        see it as "already taken" and refuse it.
        """
        cumulative = self._cumulative_skill_points(level)

        perks: dict[int, list[int]] = {}
        for lv in range(2, level + 1):
            plan = self._state.level_plans.get(lv)
            if plan and plan.perk is not None and lv != level:
                perks.setdefault(lv, []).append(plan.perk)

        return Character(
            name=self._state.name,
            level=level,
            sex=self._state.sex,
            special=dict(self._state.special) if self._state.special else {},
            tagged_skills=set(self._state.tagged_skills),
            skill_points_spent=cumulative,
            traits=list(self._state.traits),
            perks=perks,
            equipment={},
        )
