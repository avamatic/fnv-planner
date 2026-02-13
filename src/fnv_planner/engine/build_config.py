"""Configuration knobs for the build engine.

Defaults match vanilla Fallout: New Vegas. Mods may override perk
intervals, skill caps, or SPECIAL budgets.
"""

from dataclasses import dataclass

from fnv_planner.models.constants import ActorValue


@dataclass(slots=True)
class BuildConfig:
    """Tuneable parameters that aren't stored in GMST records."""

    perk_every_n_levels: int = 2   # Perk at level 2, 4, 6, ...
    skill_cap: int = 100           # Max base skill value (before equipment)
    max_traits: int = 2
    num_tagged_skills: int = 3
    special_budget: int = 40       # Total SPECIAL points at creation
    special_min: int = 1
    special_max: int = 10
    include_big_guns: bool = False
    big_guns_governing_attribute: int = ActorValue.STRENGTH
