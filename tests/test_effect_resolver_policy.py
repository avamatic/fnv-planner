"""Unit tests for EffectResolver strict/permissive condition policy."""

from fnv_planner.models.effect import (
    EffectCondition,
    Enchantment,
    EnchantmentEffect,
    MagicEffect,
)
from fnv_planner.parser.effect_resolver import EffectResolver


def _resolver(policy: str) -> EffectResolver:
    mgefs = {
        1: MagicEffect(
            form_id=1,
            editor_id="IncreaseLuck",
            name="Increase Luck",
            archetype=0,
            actor_value=11,
        )
    }
    enchs = {
        10: Enchantment(
            form_id=10,
            editor_id="EnchTest",
            name="Test Ench",
            enchantment_type=3,
            effects=[
                EnchantmentEffect(
                    mgef_form_id=1,
                    magnitude=1,
                    area=0,
                    duration=0,
                    effect_type=0,
                    actor_value=11,
                    conditions=[
                        EffectCondition(
                            function=449,
                            operator="==",
                            value=1.0,
                            param1=0x1234,
                            param2=0,
                        )
                    ],
                )
            ],
        )
    }
    return EffectResolver(mgefs, enchs, condition_policy=policy)


def test_conditional_effect_excluded_in_strict_mode():
    resolver = _resolver("strict")
    effects = resolver.resolve_enchantment(10)
    assert effects == []


def test_conditional_effect_included_in_permissive_mode():
    resolver = _resolver("permissive")
    effects = resolver.resolve_enchantment(10)
    assert len(effects) == 1
    assert effects[0].actor_value_name == "Luck"
    assert effects[0].magnitude == 1.0
    assert effects[0].is_conditional is True
