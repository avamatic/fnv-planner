"""Tests for effect_parser — integration tests against real ESM data.

Verifies MGEF and ENCH parsing counts and specific well-known effects.
"""

from pathlib import Path

import pytest

from fnv_planner.parser.effect_parser import parse_all_enchs, parse_all_mgefs


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
def mgefs(esm_data):
    return parse_all_mgefs(esm_data)


@pytest.fixture(scope="module")
def mgef_by_edid(mgefs):
    return {m.editor_id: m for m in mgefs}


@pytest.fixture(scope="module")
def enchs(esm_data):
    return parse_all_enchs(esm_data)


@pytest.fixture(scope="module")
def ench_by_edid(enchs):
    return {e.editor_id: e for e in enchs}


# --- MGEF count tests ---

def test_total_mgef_count(mgefs):
    assert len(mgefs) == 289


def test_value_modifier_count(mgefs):
    vm = [m for m in mgefs if m.is_value_modifier]
    assert len(vm) == 164


# --- Specific MGEF tests ---

def test_increase_luck(mgef_by_edid):
    """IncreaseLuck: archetype 0, actor_value 11 (Luck)."""
    m = mgef_by_edid["IncreaseLuck"]
    assert m.archetype == 0
    assert m.actor_value == 11
    assert m.is_value_modifier


def test_increase_perception(mgef_by_edid):
    """IncreasePerception: archetype 0, actor_value 6."""
    m = mgef_by_edid["IncreasePerception"]
    assert m.archetype == 0
    assert m.actor_value == 6
    assert m.is_value_modifier


def test_non_value_modifier(mgefs):
    """There should be MGEFs with archetype != 0 that are NOT value modifiers."""
    non_vm = [m for m in mgefs if not m.is_value_modifier]
    assert len(non_vm) > 0


# --- ENCH count tests ---

def test_total_ench_count(enchs):
    assert len(enchs) == 145


def test_apparel_ench_count(enchs):
    apparel = [e for e in enchs if e.enchantment_type == 3]
    assert len(apparel) == 88


def test_weapon_ench_count(enchs):
    weapons = [e for e in enchs if e.enchantment_type == 2]
    assert len(weapons) == 57


# --- Specific ENCH tests ---

def test_lucky_shades_enchantment(ench_by_edid):
    """EnchClothingLuckyShades should have 2 effects."""
    e = ench_by_edid["EnchClothingLuckyShades"]
    assert e.enchantment_type == 3  # apparel
    assert len(e.effects) == 2


def test_ench_has_effects(enchs):
    """Every enchantment should have at least one effect."""
    for e in enchs:
        assert len(e.effects) >= 1, f"ENCH {e.editor_id} has no effects"
