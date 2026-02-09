"""Tests for DerivedStats — formula verification with known inputs."""

import pytest

from fnv_planner.models.derived_stats import DerivedStats
from fnv_planner.models.game_settings import GameSettings


@pytest.fixture
def calc():
    """DerivedStats with vanilla defaults."""
    return DerivedStats(GameSettings.defaults())


# --- Hit Points ---

def test_hp_level_1_end_5(calc):
    """Level 1, END 5: 100 + 5*20 + 0*5 = 200."""
    assert calc.hit_points(endurance=5, level=1) == 200


def test_hp_level_1_end_10(calc):
    """Level 1, END 10: 100 + 10*20 + 0 = 300."""
    assert calc.hit_points(endurance=10, level=1) == 300


def test_hp_level_30_end_5(calc):
    """Level 30, END 5: 100 + 5*20 + 29*5 = 345."""
    assert calc.hit_points(endurance=5, level=30) == 345


def test_hp_level_50_end_10(calc):
    """Level 50, END 10: 100 + 10*20 + 49*5 = 545."""
    assert calc.hit_points(endurance=10, level=50) == 545


# --- Action Points ---

def test_ap_agi_5(calc):
    """AGI 5: 65 + 5*3 = 80."""
    assert calc.action_points(agility=5) == 80


def test_ap_agi_10(calc):
    """AGI 10: 65 + 10*3 = 95."""
    assert calc.action_points(agility=10) == 95


def test_ap_agi_1(calc):
    """AGI 1: 65 + 1*3 = 68."""
    assert calc.action_points(agility=1) == 68


# --- Carry Weight ---

def test_cw_str_5(calc):
    """STR 5: 150 + 5*10 = 200."""
    assert calc.carry_weight(strength=5) == pytest.approx(200.0)


def test_cw_str_10(calc):
    """STR 10: 150 + 10*10 = 250."""
    assert calc.carry_weight(strength=10) == pytest.approx(250.0)


def test_cw_str_1(calc):
    """STR 1: 150 + 1*10 = 160."""
    assert calc.carry_weight(strength=1) == pytest.approx(160.0)


# --- Critical Chance ---

def test_crit_luck_5(calc):
    """LCK 5: 0 + 5*1 = 5%."""
    assert calc.crit_chance(luck=5) == pytest.approx(5.0)


def test_crit_luck_10(calc):
    """LCK 10: 0 + 10*1 = 10%."""
    assert calc.crit_chance(luck=10) == pytest.approx(10.0)


def test_crit_luck_1(calc):
    """LCK 1: 0 + 1*1 = 1%."""
    assert calc.crit_chance(luck=1) == pytest.approx(1.0)


# --- Melee Damage ---

def test_melee_str_5(calc):
    """STR 5: 5 * 0.5 = 2.5."""
    assert calc.melee_damage(strength=5) == pytest.approx(2.5)


def test_melee_str_10(calc):
    """STR 10: 10 * 0.5 = 5.0."""
    assert calc.melee_damage(strength=10) == pytest.approx(5.0)


# --- Unarmed Damage ---

def test_unarmed_skill_0(calc):
    """Unarmed skill 0: 0.5 + 0*0.05 = 0.5."""
    assert calc.unarmed_damage(unarmed_skill=0) == pytest.approx(0.5)


def test_unarmed_skill_100(calc):
    """Unarmed skill 100: 0.5 + 100*0.05 = 5.5."""
    assert calc.unarmed_damage(unarmed_skill=100) == pytest.approx(5.5)


# --- Poison Resistance ---

def test_poison_resist_end_5(calc):
    """END 5: (5-1)*5 = 20%."""
    assert calc.poison_resistance(endurance=5) == pytest.approx(20.0)


def test_poison_resist_end_1(calc):
    """END 1: (1-1)*5 = 0%."""
    assert calc.poison_resistance(endurance=1) == pytest.approx(0.0)


# --- Rad Resistance ---

def test_rad_resist_end_5(calc):
    """END 5: (5-1)*2 = 8%."""
    assert calc.rad_resistance(endurance=5) == pytest.approx(8.0)


def test_rad_resist_end_10(calc):
    """END 10: (10-1)*2 = 18%."""
    assert calc.rad_resistance(endurance=10) == pytest.approx(18.0)


# --- Skill Points Per Level ---

def test_skill_pts_int_5(calc):
    """INT 5: 11 + floor(5*0.5) = 11 + 2 = 13."""
    assert calc.skill_points_per_level(intelligence=5) == 13


def test_skill_pts_int_10(calc):
    """INT 10: 11 + floor(10*0.5) = 11 + 5 = 16."""
    assert calc.skill_points_per_level(intelligence=10) == 16


def test_skill_pts_int_1(calc):
    """INT 1: 11 + floor(1*0.5) = 11 + 0 = 11."""
    assert calc.skill_points_per_level(intelligence=1) == 11


# --- Initial Skill ---

def test_initial_skill_gov5_luck5(calc):
    """Governing attr 5, LCK 5: 2 + 5*2 + ceil(5*0.5) = 2 + 10 + 3 = 15."""
    assert calc.initial_skill(governing_attr=5, luck=5) == 15


def test_initial_skill_gov10_luck10(calc):
    """Governing attr 10, LCK 10: 2 + 10*2 + ceil(10*0.5) = 2 + 20 + 5 = 27."""
    assert calc.initial_skill(governing_attr=10, luck=10) == 27


def test_initial_skill_gov1_luck1(calc):
    """Governing attr 1, LCK 1: 2 + 1*2 + ceil(1*0.5) = 2 + 2 + 1 = 5."""
    assert calc.initial_skill(governing_attr=1, luck=1) == 5


# --- Tag Bonus ---

def test_tag_bonus(calc):
    """Tag bonus should be 15 in vanilla."""
    assert calc.tag_bonus() == 15


# --- Companion Nerve ---

def test_companion_nerve_cha_5(calc):
    """CHA 5: 5 * 5 = 25%."""
    assert calc.companion_nerve(charisma=5) == pytest.approx(25.0)


def test_companion_nerve_cha_10(calc):
    """CHA 10: 10 * 5 = 50%."""
    assert calc.companion_nerve(charisma=10) == pytest.approx(50.0)


# --- Max Level ---

def test_max_level(calc):
    """Vanilla max level is 50 (with DLCs; base game is 30)."""
    assert calc.max_level() == 50


# --- Custom GMST override ---

def test_custom_gmst_overrides_formula():
    """A modded GMST should change the formula output."""
    modded = GameSettings(_values={"fAVDCarryWeightsBase": 200.0, "fAVDCarryWeightMult": 15.0})
    calc = DerivedStats(modded)
    # STR 5: 200 + 5*15 = 275
    assert calc.carry_weight(strength=5) == pytest.approx(275.0)
