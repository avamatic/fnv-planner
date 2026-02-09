"""FNV actor values, condition functions, and comparison operators.

Actor value indices come from the GECK wiki. Only SPECIAL and skills are
relevant for perk requirements; the rest are included for reference.
"""

from enum import IntEnum


class ActorValue(IntEnum):
    """Actor value indices used in CTDA conditions.

    SPECIAL stats are indices 5-11, skills are 32-45 in FNV.
    """
    # SPECIAL
    STRENGTH = 5
    PERCEPTION = 6
    ENDURANCE = 7
    CHARISMA = 8
    INTELLIGENCE = 9
    AGILITY = 10
    LUCK = 11

    # Skills
    BARTER = 32
    BIG_GUNS = 33       # Not used in FNV, but index exists
    ENERGY_WEAPONS = 34
    EXPLOSIVES = 35
    LOCKPICK = 36
    MEDICINE = 37
    MELEE_WEAPONS = 38
    REPAIR = 39
    SCIENCE = 40
    GUNS = 41           # "Small Guns" in FO3
    SNEAK = 42
    SPEECH = 43
    SURVIVAL = 44
    UNARMED = 45


# Friendly display names
ACTOR_VALUE_NAMES: dict[int, str] = {
    5: "Strength",
    6: "Perception",
    7: "Endurance",
    8: "Charisma",
    9: "Intelligence",
    10: "Agility",
    11: "Luck",
    # Derived stats (used by enchantments/consumables)
    12: "Action Points",
    14: "Critical Chance",
    16: "Health",
    20: "Rad Resistance",
    25: "Head Condition",
    54: "Rads",
    73: "Dehydration",
    74: "Hunger",
    75: "Sleep Deprivation",
    76: "Night Eye",
    # Regular skills
    32: "Barter",
    33: "Big Guns",      # Not used in FNV, but index exists
    34: "Energy Weapons",
    35: "Explosives",
    36: "Lockpick",
    37: "Medicine",
    38: "Melee Weapons",
    39: "Repair",
    40: "Science",
    41: "Guns",
    42: "Sneak",
    43: "Speech",
    44: "Survival",
    45: "Unarmed",
}

# Set of SPECIAL indices for easy checking
SPECIAL_INDICES = frozenset(range(5, 12))
SKILL_INDICES = frozenset(range(32, 46))


class ConditionFunction(IntEnum):
    """Condition function indices used in CTDA subrecords."""
    GET_IS_SEX = 70
    GET_LEVEL = 80
    HAS_PERK = 372
    GET_IS_REFERENCE = 449
    GET_PERMANENT_ACTOR_VALUE = 495


class MagicEffectArchetype(IntEnum):
    """MGEF archetype — only VALUE_MODIFIER matters for stat planning."""
    VALUE_MODIFIER = 0
    SCRIPT = 1


class EquipmentSlot(IntEnum):
    """Equipment type index from ETYP subrecord."""
    BIG_GUNS = 0        # Not used in FNV
    ENERGY_WEAPONS = 1
    EXPLOSIVES = 2
    MELEE_WEAPONS = 3
    UNARMED = 4
    GUNS = 5            # "Small Guns" slot
    NONE = -1           # No slot / not equippable


# Maps BOOK skill_index (0-13) to ActorValue index (32-45)
SKILL_INDEX_TO_ACTOR_VALUE: dict[int, int] = {
    i: i + 32 for i in range(14)
}


class ComparisonOperator(IntEnum):
    """Comparison operators encoded in the CTDA type byte (bits 5-7)."""
    EQUAL = 0          # ==
    NOT_EQUAL = 1      # !=
    GREATER = 2        # >
    GREATER_EQUAL = 3  # >=
    LESS = 4           # <
    LESS_EQUAL = 5     # <=


COMPARISON_SYMBOLS: dict[int, str] = {
    0: "==",
    1: "!=",
    2: ">",
    3: ">=",
    4: "<",
    5: "<=",
}


# Governing SPECIAL attribute for each skill — engine-hardcoded, not moddable.
# Used to compute initial skill values: 2 + governing_attr * 2 + ceil(luck * 0.5)
AV = ActorValue
SKILL_GOVERNING_ATTRIBUTE: dict[int, int] = {
    AV.BARTER: AV.CHARISMA,
    AV.ENERGY_WEAPONS: AV.PERCEPTION,
    AV.EXPLOSIVES: AV.PERCEPTION,
    AV.GUNS: AV.AGILITY,
    AV.LOCKPICK: AV.PERCEPTION,
    AV.MEDICINE: AV.INTELLIGENCE,
    AV.MELEE_WEAPONS: AV.STRENGTH,
    AV.REPAIR: AV.INTELLIGENCE,
    AV.SCIENCE: AV.INTELLIGENCE,
    AV.SNEAK: AV.AGILITY,
    AV.SPEECH: AV.CHARISMA,
    AV.SURVIVAL: AV.ENDURANCE,
    AV.UNARMED: AV.ENDURANCE,
}
