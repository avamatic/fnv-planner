"""Tests for item_parser — integration tests against real ESM data.

Verifies ARMO, WEAP, ALCH, and BOOK parsing counts and specific items.
"""

from pathlib import Path

import pytest

from fnv_planner.models.game_settings import GameSettings
from fnv_planner.parser.item_parser import (
    parse_all_armors,
    parse_all_books,
    parse_all_consumables,
    parse_all_weapons,
)


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
def armors(esm_data):
    return parse_all_armors(esm_data)


@pytest.fixture(scope="module")
def armor_by_edid(armors):
    return {a.editor_id: a for a in armors}


@pytest.fixture(scope="module")
def weapons(esm_data):
    return parse_all_weapons(esm_data)


@pytest.fixture(scope="module")
def weapon_by_edid(weapons):
    return {w.editor_id: w for w in weapons}


@pytest.fixture(scope="module")
def consumables(esm_data):
    return parse_all_consumables(esm_data)


@pytest.fixture(scope="module")
def consumable_by_edid(consumables):
    return {c.editor_id: c for c in consumables}


@pytest.fixture(scope="module")
def books(esm_data):
    return parse_all_books(esm_data)

@pytest.fixture(scope="module")
def gmst(esm_data):
    return GameSettings.from_esm(esm_data)


@pytest.fixture(scope="module")
def book_by_edid(books):
    return {b.editor_id: b for b in books}


# --- ARMO count tests ---

def test_total_armor_count(armors):
    assert len(armors) == 389


def test_playable_armor_count(armors):
    playable = [a for a in armors if a.is_playable]
    assert len(playable) > 0


def test_enchanted_armor_count(armors):
    enchanted = [a for a in armors if a.enchantment_form_id is not None]
    assert len(enchanted) > 0


# --- Specific ARMO tests ---

def test_lucky_shades_armor(armor_by_edid):
    """Lucky Shades should be playable, enchanted, DT 0."""
    a = armor_by_edid["UniqueGlassesLuckyShades"]
    assert a.name == "Lucky Shades"
    assert a.is_playable
    assert a.enchantment_form_id is not None
    assert a.damage_threshold == 0.0


def test_unenchanted_armor_exists(armors):
    """Some armor should have no enchantment."""
    unenchanted = [a for a in armors if a.enchantment_form_id is None]
    assert len(unenchanted) > 0


# --- WEAP count tests ---

def test_total_weapon_count(weapons):
    assert len(weapons) == 261


# --- Specific WEAP tests ---

def test_weapon_has_damage(weapons):
    """At least some weapons should have non-zero damage."""
    with_damage = [w for w in weapons if w.damage > 0]
    assert len(with_damage) > 0


# --- ALCH count tests ---

def test_total_consumable_count(consumables):
    assert len(consumables) == 189


# --- Specific ALCH tests ---

def test_stimpak(consumable_by_edid):
    """Stimpak should exist and be medicine."""
    c = consumable_by_edid["Stimpak"]
    assert c.name == "Stimpak"
    assert c.is_medicine


def test_consumable_with_effects(consumables):
    """At least some consumables should have inline effects."""
    with_effects = [c for c in consumables if len(c.effects) > 0]
    assert len(with_effects) > 0


# --- BOOK count tests ---

def test_total_book_count(books):
    assert len(books) == 27


def test_skill_book_count(books):
    skill_books = [b for b in books if b.is_skill_book]
    assert len(skill_books) == 17


# --- Specific BOOK tests ---

def test_skill_book_has_stat_effect(books, gmst):
    """Every skill book should produce a GMST-driven stat effect."""
    book_points = gmst.skill_book_base_points()
    for b in books:
        if b.is_skill_book:
            eff = b.to_stat_effect(float(book_points))
            assert eff is not None, f"Skill book {b.editor_id} has no stat_effect"
            assert eff.magnitude == pytest.approx(float(book_points))
            assert eff.actor_value_name, f"Skill book {b.editor_id} has no AV name"


def test_non_skill_book_has_no_effect(books, gmst):
    """Non-skill books should have no stat_effect."""
    book_points = float(gmst.skill_book_base_points())
    for b in books:
        if not b.is_skill_book:
            assert b.to_stat_effect(book_points) is None, f"Non-skill book {b.editor_id} has a stat_effect"
