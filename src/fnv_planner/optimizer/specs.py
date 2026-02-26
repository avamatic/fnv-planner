"""Input specs for goal-driven build planning."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class StartingConditions:
    """Optional creation/setup inputs used to seed planning."""

    name: str | None = None
    sex: int | None = None
    special: dict[int, int] | None = None
    tagged_skills: set[int] | None = None
    traits: list[int] | None = None
    equipment: dict[int, int] | None = None
    target_level: int | None = None


@dataclass(slots=True)
class GoalSpec:
    """User goals for deterministic level-by-level planning."""

    required_perks: list[int] = field(default_factory=list)
    requirements: list["RequirementSpec"] = field(default_factory=list)
    skill_books_by_av: dict[int, int] = field(default_factory=dict)
    target_level: int | None = None
    maximize_skills: bool = True
    fill_perk_slots: bool = False


@dataclass(slots=True)
class RequirementSpec:
    """A single user-defined requirement to satisfy by planning.

    `kind`:
      - "actor_value": threshold on a skill or SPECIAL actor value
      - "perk": require owning a specific perk rank
      - "trait": require selecting a specific trait
      - "max_skills": require all skills to reach 100
      - "max_crit": maximize flat critical chance bonus via perk selection
      - "max_crit_damage": maximize crit-damage-oriented perk value
      - "experience_multiplier": threshold on XP gain multiplier (percent)
      - "damage_multiplier": threshold on outgoing damage multiplier (percent)
      - "crit_chance_bonus": threshold on flat critical chance bonus
      - "crit_damage_potential": threshold on derived crit-damage potential stat
    """

    kind: str
    priority: int = 100
    reason: str = ""
    by_level: int | None = None

    # kind="actor_value"
    actor_value: int | None = None
    operator: str = ">="
    value: int | None = None
    value_float: float | None = None

    # kind="perk"
    perk_id: int | None = None
    perk_rank: int = 1

    # kind="trait"
    trait_id: int | None = None
