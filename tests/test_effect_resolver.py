"""Tests for effect_resolver — integration tests against real ESM data.

Verifies end-to-end resolution: item → enchantment → magic effect → stat effect.
"""

from pathlib import Path

import pytest

from fnv_planner.parser.effect_resolver import EffectResolver
from fnv_planner.parser.item_parser import parse_all_armors, parse_all_consumables


ESM_PATH = Path(
    "/home/am/.local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm"
)

pytestmark = pytest.mark.skipif(
    not ESM_PATH.exists(), reason="FalloutNV.esm not found"
)


@pytest.fixture(scope="module")
def esm_data():
    return ESM_PATH.read_bytes()


@pytest.fixture(scope="module")
def resolver(esm_data):
    return EffectResolver.from_esm(esm_data)


@pytest.fixture(scope="module")
def armors(esm_data):
    return parse_all_armors(esm_data)


@pytest.fixture(scope="module")
def armor_by_edid(armors):
    return {a.editor_id: a for a in armors}


@pytest.fixture(scope="module")
def consumables(esm_data):
    return parse_all_consumables(esm_data)


@pytest.fixture(scope="module")
def consumable_by_edid(consumables):
    return {c.editor_id: c for c in consumables}


# --- End-to-end armor resolution ---

def test_lucky_shades_resolved(resolver, armor_by_edid):
    """Lucky Shades → ENCH → +1 Luck, +3 Perception."""
    armor = armor_by_edid["UniqueGlassesLuckyShades"]
    resolver.resolve_armor(armor)

    effects = {e.actor_value_name: e.magnitude for e in armor.stat_effects}
    assert effects["Luck"] == 1.0
    assert effects["Perception"] == 3.0


def test_unenchanted_armor_no_effects(resolver, armors):
    """Armor without enchantment should have empty stat_effects."""
    unenchanted = [a for a in armors if a.enchantment_form_id is None]
    assert len(unenchanted) > 0
    armor = unenchanted[0]
    resolver.resolve_armor(armor)
    assert armor.stat_effects == []


def test_resolve_missing_form_id(resolver):
    """Resolving a non-existent enchantment form ID returns empty list."""
    result = resolver.resolve_enchantment(0xDEADBEEF)
    assert result == []


# --- End-to-end consumable resolution ---

def test_consumable_resolution(resolver, consumables):
    """At least some consumables should resolve to stat effects."""
    resolved_count = 0
    for c in consumables:
        resolver.resolve_consumable(c)
        if c.stat_effects:
            resolved_count += 1
    assert resolved_count > 0
