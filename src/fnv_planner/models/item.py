"""Item data models: armor, weapons, consumables, and books.

Each item type stores raw parsed fields plus a stat_effects list that
gets populated later by the EffectResolver. This separation keeps parsers
testable in isolation from effect resolution.
"""

from dataclasses import dataclass, field

from fnv_planner.models.constants import (
    ACTOR_VALUE_NAMES,
    SKILL_INDEX_TO_ACTOR_VALUE,
)
from fnv_planner.models.effect import EnchantmentEffect, StatEffect


@dataclass(slots=True)
class Armor:
    """A parsed ARMO record."""
    form_id: int
    editor_id: str
    name: str
    value: int                  # gold value
    health: int
    weight: float
    damage_threshold: float     # from DNAM
    equipment_slot: int         # ETYP index (-1 if none)
    enchantment_form_id: int | None   # EITM form ID, if enchanted
    is_playable: bool           # BMDT byte 4 bit 6 inverted
    stat_effects: list[StatEffect] = field(default_factory=list)
    conditional_effects_excluded: int = 0


@dataclass(slots=True)
class Weapon:
    """A parsed WEAP record."""
    form_id: int
    editor_id: str
    name: str
    value: int
    health: int
    weight: float
    damage: int                 # base damage (uint16)
    clip_size: int              # uint8
    crit_damage: int            # uint16
    crit_multiplier: float      # float32
    equipment_slot: int         # ETYP index
    enchantment_form_id: int | None
    is_playable: bool           # header flag bit 2 inverted (non-playable flag)
    weapon_flags_1: int = 0     # WEAP DNAM Flags1 (u8), when available
    weapon_flags_2: int = 0     # WEAP DNAM Flags2 (u32), when available
    stat_effects: list[StatEffect] = field(default_factory=list)
    conditional_effects_excluded: int = 0

    @property
    def is_non_playable_flagged(self) -> bool:
        # GetWeaponFlags1 bit 7: weapon is non-playable.
        return bool(self.weapon_flags_1 & 0x80)

    @property
    def is_embedded_weapon(self) -> bool:
        # GetWeaponFlags1 bit 5: weapon is embedded.
        return bool(self.weapon_flags_1 & 0x20)


@dataclass(slots=True)
class Consumable:
    """A parsed ALCH record (chems, food, drinks)."""
    form_id: int
    editor_id: str
    name: str
    weight: float               # from DATA (4 bytes)
    value: int                  # from ENIT
    flags: int                  # ENIT byte 4 (bit 1=food, bit 2=medicine)
    withdrawal_effect: int      # form ID from ENIT (0 if none)
    addiction_chance: float     # from ENIT
    effects: list[EnchantmentEffect] = field(default_factory=list)  # inline EFID/EFIT
    stat_effects: list[StatEffect] = field(default_factory=list)
    conditional_effects_excluded: int = 0

    @property
    def is_food(self) -> bool:
        return bool(self.flags & 0x02)

    @property
    def is_medicine(self) -> bool:
        return bool(self.flags & 0x04)


@dataclass(slots=True)
class Book:
    """A parsed BOOK record — may be a skill book."""
    form_id: int
    editor_id: str
    name: str
    value: int
    weight: float
    skill_index: int            # -1 if not a skill book, 0-13 otherwise

    @property
    def is_skill_book(self) -> bool:
        return self.skill_index >= 0

    @property
    def skill_actor_value(self) -> int | None:
        """ActorValue index for the skill this book teaches, or None."""
        if self.skill_index < 0:
            return None
        return SKILL_INDEX_TO_ACTOR_VALUE.get(self.skill_index)

    @property
    def skill_name(self) -> str | None:
        av = self.skill_actor_value
        if av is None:
            return None
        return ACTOR_VALUE_NAMES.get(av, f"AV{av}")

    def to_stat_effect(self, skill_points: float) -> StatEffect | None:
        """Build a StatEffect for this skill book with caller-provided points."""
        av = self.skill_actor_value
        if av is None:
            return None
        return StatEffect(
            actor_value=av,
            actor_value_name=ACTOR_VALUE_NAMES.get(av, f"AV{av}"),
            magnitude=float(skill_points),
        )
