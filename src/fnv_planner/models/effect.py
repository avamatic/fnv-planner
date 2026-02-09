"""Magic effect and enchantment data models.

The stat-bonus chain in FNV is: item → enchantment → magic effect → actor value.
These models represent the bottom two layers (MGEF and ENCH records) plus the
resolved output (StatEffect) used throughout the planner.
"""

from dataclasses import dataclass, field

from fnv_planner.models.constants import MagicEffectArchetype


@dataclass(slots=True)
class StatEffect:
    """A resolved stat modifier: 'this gives +1 Luck' or 'deals -2 Health/sec for 10sec'.

    This is the final output consumed by the rest of the planner.
    """
    actor_value: int       # ActorValue index (e.g. 11 for Luck)
    actor_value_name: str  # friendly name (e.g. "Luck")
    magnitude: float       # amount (e.g. 1.0 or -2.0)
    duration: int = 0      # seconds (0 = instant/permanent)
    is_hostile: bool = False  # True = affects enemies (weapon), False = affects player


@dataclass(slots=True)
class MagicEffect:
    """A parsed MGEF record.

    Only effects with archetype VALUE_MODIFIER and a valid actor_value
    produce stat bonuses. Everything else (scripts, abilities, etc.)
    is tracked but doesn't feed into build planning.
    """
    form_id: int
    editor_id: str
    name: str
    archetype: int       # MagicEffectArchetype value
    actor_value: int     # -1 if not applicable

    @property
    def is_value_modifier(self) -> bool:
        return self.archetype == MagicEffectArchetype.VALUE_MODIFIER and self.actor_value >= 0


@dataclass(slots=True)
class EnchantmentEffect:
    """One EFID+EFIT pair within an enchantment or consumable.

    EFID gives the MGEF form ID; EFIT gives magnitude and other fields.
    """
    mgef_form_id: int    # links to a MagicEffect
    magnitude: int       # unsigned, from EFIT
    area: int
    duration: int
    effect_type: int     # 0=self, 1=touch, 2=target
    actor_value: int     # signed, from EFIT (-1 if not applicable)


@dataclass(slots=True)
class Enchantment:
    """A parsed ENCH record — a bundle of magic effects applied by an item."""
    form_id: int
    editor_id: str
    name: str
    enchantment_type: int  # 2=weapon, 3=apparel
    effects: list[EnchantmentEffect] = field(default_factory=list)
