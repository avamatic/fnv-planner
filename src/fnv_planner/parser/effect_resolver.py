"""Resolve enchantment form IDs into concrete stat effects.

The resolver bridges parsed items and the MGEF/ENCH records they reference.
Parsers store raw form IDs; the resolver walks the chain
(item → ENCH → EFID → MGEF) and populates each item's stat_effects list.
"""

from fnv_planner.models.constants import ACTOR_VALUE_NAMES
from fnv_planner.models.effect import (
    Enchantment,
    EnchantmentEffect,
    MagicEffect,
    StatEffect,
)
from fnv_planner.models.item import Armor, Consumable, Weapon


class EffectResolver:
    """Resolves enchantment/effect form IDs into StatEffect lists.

    Build once from ESM data, then call resolve_* methods on parsed items.
    """

    def __init__(
        self,
        mgefs: dict[int, MagicEffect],
        enchs: dict[int, Enchantment],
    ) -> None:
        self._mgefs = mgefs
        self._enchs = enchs

    @classmethod
    def from_esm(cls, data: bytes) -> "EffectResolver":
        """Parse MGEF and ENCH GRUPs and build lookup dicts."""
        from fnv_planner.parser.effect_parser import parse_all_enchs, parse_all_mgefs

        mgefs = {m.form_id: m for m in parse_all_mgefs(data)}
        enchs = {e.form_id: e for e in parse_all_enchs(data)}
        return cls(mgefs, enchs)

    def resolve_enchantment(self, ench_form_id: int) -> list[StatEffect]:
        """Walk ENCH → EFID → MGEF and return stat effects for value modifiers."""
        ench = self._enchs.get(ench_form_id)
        if ench is None:
            return []
        # Type 2 = weapon enchantments (hostile, damage to enemies)
        # Type 3 = apparel enchantments (beneficial, buffs to wearer)
        is_hostile = ench.enchantment_type == 2
        return self.resolve_inline_effects(ench.effects, is_hostile=is_hostile)

    def resolve_inline_effects(
        self,
        effects: list[EnchantmentEffect],
        is_hostile: bool = False,
    ) -> list[StatEffect]:
        """Resolve a list of EFID/EFIT pairs (used by both ENCH and ALCH).

        Args:
            effects: List of enchantment effects to resolve
            is_hostile: If True, negate magnitudes (for weapon enchantments that deal damage)
        """
        result: list[StatEffect] = []
        for eff in effects:
            mgef = self._mgefs.get(eff.mgef_form_id)
            if mgef is None or not mgef.is_value_modifier:
                continue
            av = mgef.actor_value
            magnitude = float(eff.magnitude)
            # Weapon enchantments deal damage/debuffs (hostile) → negative magnitude
            # Apparel enchantments and consumables provide buffs → positive magnitude
            if is_hostile:
                magnitude = -magnitude
            result.append(StatEffect(
                actor_value=av,
                actor_value_name=ACTOR_VALUE_NAMES.get(av, f"AV{av}"),
                magnitude=magnitude,
                duration=eff.duration,
                is_hostile=is_hostile,
            ))
        return result

    def resolve_armor(self, armor: Armor) -> None:
        """Populate an Armor's stat_effects from its enchantment."""
        if armor.enchantment_form_id is not None:
            armor.stat_effects = self.resolve_enchantment(armor.enchantment_form_id)

    def resolve_weapon(self, weapon: Weapon) -> None:
        """Populate a Weapon's stat_effects from its enchantment."""
        if weapon.enchantment_form_id is not None:
            weapon.stat_effects = self.resolve_enchantment(weapon.enchantment_form_id)

    def resolve_consumable(self, consumable: Consumable) -> None:
        """Populate a Consumable's stat_effects from its inline effects."""
        consumable.stat_effects = self.resolve_inline_effects(consumable.effects)
