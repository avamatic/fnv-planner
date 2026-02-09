"""Character build data model.

Represents a player's build choices: SPECIAL allocation, tagged skills,
skill points spent per level, traits, perks, and equipped items.
This is the core input to the derived stats calculator.
"""

from dataclasses import dataclass, field

from fnv_planner.models.constants import ActorValue


# Default SPECIAL: all stats at 5 (the starting allocation before the player
# redistributes their 33 points across 7 stats, min 1 max 10).
_DEFAULT_SPECIAL: dict[int, int] = {
    ActorValue.STRENGTH: 5,
    ActorValue.PERCEPTION: 5,
    ActorValue.ENDURANCE: 5,
    ActorValue.CHARISMA: 5,
    ActorValue.INTELLIGENCE: 5,
    ActorValue.AGILITY: 5,
    ActorValue.LUCK: 5,
}


@dataclass
class Character:
    """A Fallout: New Vegas character build.

    All stat references use ActorValue indices for consistency with the
    engine's internal representation.
    """

    # Identity
    name: str = "Courier"
    level: int = 1
    sex: int | None = None  # 0=Male, 1=Female, None=unset

    # SPECIAL — keyed by ActorValue index (5-11), values 1-10
    special: dict[int, int] = field(default_factory=lambda: dict(_DEFAULT_SPECIAL))

    # Skills — AV indices of up to 3 tagged skills
    tagged_skills: set[int] = field(default_factory=set)

    # Skill points invested via level-up, keyed by AV index
    skill_points_spent: dict[int, int] = field(default_factory=dict)

    # Traits (max 2, from perks with is_trait=True) — perk form IDs
    traits: list[int] = field(default_factory=list)

    # Perks chosen at each level — level → [perk form IDs]
    perks: dict[int, list[int]] = field(default_factory=dict)

    # Equipment — slot index → item form ID
    equipment: dict[int, int] = field(default_factory=dict)
