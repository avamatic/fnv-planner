"""Tests for Character model and full stat computation pipeline."""

from pathlib import Path

import pytest

from fnv_planner.models.character import Character
from fnv_planner.models.constants import ActorValue, SKILL_GOVERNING_ATTRIBUTE
from fnv_planner.models.derived_stats import (
    CharacterStats,
    DerivedStats,
    compute_equipment_bonuses,
    compute_stats,
)
from fnv_planner.models.effect import StatEffect
from fnv_planner.models.game_settings import GameSettings, _VANILLA_DEFAULTS
from fnv_planner.models.item import Armor, Weapon


ESM_PATH = Path(
    "/home/am/.local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm"
)

AV = ActorValue


# --- GameSettings defaults ---

def test_defaults_has_all_keys():
    """GameSettings.defaults() should have all expected GMST keys."""
    gs = GameSettings.defaults()
    for key in _VANILLA_DEFAULTS:
        if key.startswith("f"):
            val = gs.get_float(key, -999.0)
            assert val != -999.0, f"Missing float GMST: {key}"
        elif key.startswith("i"):
            val = gs.get_int(key, -999)
            assert val != -999, f"Missing int GMST: {key}"


def test_defaults_carry_weight_base():
    gs = GameSettings.defaults()
    assert gs.get_float("fAVDCarryWeightsBase", 0.0) == pytest.approx(150.0)


def test_defaults_max_level():
    gs = GameSettings.defaults()
    assert gs.get_int("iMaxCharacterLevel", 0) == 50


def test_defaults_skill_book_base_points():
    gs = GameSettings.defaults()
    assert gs.skill_book_base_points() == 3


def test_get_float_missing_returns_default():
    gs = GameSettings(_values={})
    assert gs.get_float("nonexistent", 42.0) == pytest.approx(42.0)


def test_get_int_missing_returns_default():
    gs = GameSettings(_values={})
    assert gs.get_int("nonexistent", 99) == 99


# --- Character defaults ---

def test_default_character():
    """Default character has all SPECIAL at 5, level 1, no tags/perks."""
    c = Character()
    assert c.name == "Courier"
    assert c.level == 1
    assert len(c.special) == 7
    for av in range(AV.STRENGTH, AV.LUCK + 1):
        assert c.special[av] == 5
    assert len(c.tagged_skills) == 0
    assert len(c.skill_points_spent) == 0
    assert len(c.traits) == 0
    assert len(c.perks) == 0
    assert len(c.equipment) == 0


def test_character_independent_defaults():
    """Each Character instance gets its own mutable copies."""
    c1 = Character()
    c2 = Character()
    c1.special[AV.STRENGTH] = 10
    assert c2.special[AV.STRENGTH] == 5


# --- Skill computation ---

def test_initial_skills_all_5s():
    """With all SPECIAL at 5, every skill starts at 15 (2 + 5*2 + ceil(5*0.5))."""
    c = Character()
    gmst = GameSettings.defaults()
    stats = compute_stats(c, gmst)
    for skill_av, gov_av in SKILL_GOVERNING_ATTRIBUTE.items():
        assert stats.skills[skill_av] == 15, (
            f"Skill AV {skill_av} expected 15, got {stats.skills[skill_av]}"
        )


def test_tagged_skill_bonus():
    """Tagged skills get +15 bonus."""
    c = Character()
    c.tagged_skills = {AV.GUNS, AV.LOCKPICK, AV.SPEECH}
    gmst = GameSettings.defaults()
    stats = compute_stats(c, gmst)
    # Tagged: 15 + 15 = 30
    assert stats.skills[AV.GUNS] == 30
    assert stats.skills[AV.LOCKPICK] == 30
    assert stats.skills[AV.SPEECH] == 30
    # Untagged: still 15
    assert stats.skills[AV.BARTER] == 15


def test_skill_points_spent():
    """Invested skill points add directly to skill value."""
    c = Character()
    c.skill_points_spent = {AV.SCIENCE: 20, AV.REPAIR: 10}
    gmst = GameSettings.defaults()
    stats = compute_stats(c, gmst)
    assert stats.skills[AV.SCIENCE] == 35  # 15 + 20
    assert stats.skills[AV.REPAIR] == 25   # 15 + 10
    assert stats.skills[AV.BARTER] == 15   # untouched


def test_skill_with_high_governing_attr():
    """Higher governing attribute increases initial skill value."""
    c = Character()
    c.special[AV.PERCEPTION] = 10  # Governs Lockpick, Energy Weapons, Explosives
    gmst = GameSettings.defaults()
    stats = compute_stats(c, gmst)
    # Lockpick: 2 + 10*2 + ceil(5*0.5) = 2 + 20 + 3 = 25
    assert stats.skills[AV.LOCKPICK] == 25
    # Barter (governed by CHA=5): still 15
    assert stats.skills[AV.BARTER] == 15


def test_skill_with_high_luck():
    """Higher luck increases all skill values."""
    c = Character()
    c.special[AV.LUCK] = 10
    gmst = GameSettings.defaults()
    stats = compute_stats(c, gmst)
    # Each skill: 2 + 5*2 + ceil(10*0.5) = 2 + 10 + 5 = 17
    assert stats.skills[AV.BARTER] == 17


def test_skill_base_uses_gmst_per_skill_value():
    """Per-skill base should come from fAVDSkill*Base GMST keys."""
    c = Character()
    gmst = GameSettings(_values={"fAVDSkillScienceBase": 6.0})
    stats = compute_stats(c, gmst)
    # Science: 6 + INT(5)*2 + ceil(LCK(5)*0.5=2.5->3) = 19
    assert stats.skills[AV.SCIENCE] == 19
    # Barter still uses default base fallback 2 -> 15
    assert stats.skills[AV.BARTER] == 15


# --- Equipment bonuses ---

def test_equipment_bonus_flows_to_special():
    """Equipment SPECIAL bonus affects effective_special and derived stats."""
    c = Character()
    # Equip an item that gives +3 STR
    fake_armor = Armor(
        form_id=0xAAAA, editor_id="TestArmor", name="Power Armor",
        value=100, health=500, weight=30.0, damage_threshold=20.0,
        equipment_slot=0, enchantment_form_id=None, is_playable=True,
        stat_effects=[
            StatEffect(actor_value=AV.STRENGTH, actor_value_name="Strength",
                       magnitude=3.0, duration=0, is_hostile=False),
        ],
    )
    c.equipment[0] = 0xAAAA
    armors = {0xAAAA: fake_armor}
    gmst = GameSettings.defaults()
    stats = compute_stats(c, gmst, armors=armors)
    # Effective STR = 5 + 3 = 8
    assert stats.effective_special[AV.STRENGTH] == 8
    # Carry weight = 150 + 8*10 = 230
    assert stats.carry_weight == pytest.approx(230.0)


def test_equipment_skill_bonus():
    """Equipment skill bonus flows into final skill values."""
    c = Character()
    fake_armor = Armor(
        form_id=0xBBBB, editor_id="SkillArmor", name="Lab Coat",
        value=10, health=100, weight=1.0, damage_threshold=0.0,
        equipment_slot=0, enchantment_form_id=None, is_playable=True,
        stat_effects=[
            StatEffect(actor_value=AV.SCIENCE, actor_value_name="Science",
                       magnitude=5.0, duration=0, is_hostile=False),
        ],
    )
    c.equipment[0] = 0xBBBB
    armors = {0xBBBB: fake_armor}
    gmst = GameSettings.defaults()
    stats = compute_stats(c, gmst, armors=armors)
    # Science: 15 (base) + 5 (equipment) = 20
    assert stats.skills[AV.SCIENCE] == 20


def test_hostile_weapon_effects_excluded():
    """Hostile weapon effects should not count as player bonuses."""
    from fnv_planner.models.item import Weapon

    c = Character()
    fake_weapon = Weapon(
        form_id=0xCCCC, editor_id="TestGun", name="Laser Pistol",
        value=50, health=200, weight=3.0, damage=20, clip_size=24,
        crit_damage=20, crit_multiplier=1.0, equipment_slot=1,
        enchantment_form_id=None, is_playable=True,
        stat_effects=[
            StatEffect(actor_value=16, actor_value_name="Health",
                       magnitude=-50.0, duration=0, is_hostile=True),
        ],
    )
    c.equipment[1] = 0xCCCC
    weapons = {0xCCCC: fake_weapon}
    bonuses = compute_equipment_bonuses(c, {}, weapons)
    assert len(bonuses) == 0


def test_timed_effects_excluded():
    """Timed effects (duration > 0) should not count as permanent bonuses."""
    c = Character()
    fake_armor = Armor(
        form_id=0xDDDD, editor_id="TimedArmor", name="Temp Buff",
        value=10, health=100, weight=1.0, damage_threshold=0.0,
        equipment_slot=0, enchantment_form_id=None, is_playable=True,
        stat_effects=[
            StatEffect(actor_value=AV.AGILITY, actor_value_name="Agility",
                       magnitude=2.0, duration=60, is_hostile=False),
        ],
    )
    c.equipment[0] = 0xDDDD
    armors = {0xDDDD: fake_armor}
    bonuses = compute_equipment_bonuses(c, armors, {})
    assert len(bonuses) == 0


# --- Full pipeline ---

def test_compute_stats_returns_character_stats():
    """compute_stats returns a CharacterStats with all fields populated."""
    c = Character()
    gmst = GameSettings.defaults()
    stats = compute_stats(c, gmst)
    assert isinstance(stats, CharacterStats)
    assert stats.hit_points == 200   # END 5, level 1
    assert stats.action_points == 80  # AGI 5
    assert stats.carry_weight == pytest.approx(200.0)  # STR 5
    assert stats.crit_chance == pytest.approx(5.0)     # LCK 5
    assert stats.crit_damage_potential == pytest.approx(0.0)
    assert stats.skill_points_per_level == 13  # INT 5
    assert stats.max_level == 50
    assert stats.companion_nerve == pytest.approx(25.0)  # CHA 5
    assert len(stats.skills) == 13  # 13 FNV skills (BIG_GUNS excluded)


def test_compute_stats_can_include_big_guns_when_enabled():
    c = Character()
    c.tagged_skills = {AV.BARTER, AV.BIG_GUNS, AV.GUNS}
    gmst = GameSettings.defaults()
    stats = compute_stats(
        c,
        gmst,
        include_big_guns=True,
        big_guns_governing_attribute=AV.STRENGTH,
    )
    assert AV.BIG_GUNS in stats.skills
    # Base 15 with all SPECIAL=5 + tag bonus 15
    assert stats.skills[AV.BIG_GUNS] == 30


def test_compute_stats_level_20():
    """Stats at level 20 with some build choices."""
    c = Character(
        name="Test Build",
        level=20,
    )
    c.special[AV.STRENGTH] = 7
    c.special[AV.INTELLIGENCE] = 9
    c.tagged_skills = {AV.GUNS, AV.REPAIR, AV.SCIENCE}
    c.skill_points_spent = {AV.GUNS: 50, AV.REPAIR: 30}

    gmst = GameSettings.defaults()
    stats = compute_stats(c, gmst)

    # HP: 100 + 5*20 + 19*5 = 295
    assert stats.hit_points == 295
    # Carry weight: 150 + 7*10 = 220
    assert stats.carry_weight == pytest.approx(220.0)
    # Skill pts/level: 11 + floor(9*0.5) = 11 + 4 = 15
    assert stats.skill_points_per_level == 15
    # Guns (governed by AGI=5): 2 + 5*2 + 3 = 15, + tag 15, + spent 50 = 80
    assert stats.skills[AV.GUNS] == 80


def test_crit_damage_potential_uses_best_equipped_weapon():
    c = Character()
    primary = Weapon(
        form_id=0xE001,
        editor_id="PrimaryWeapon",
        name="Primary",
        value=10,
        health=100,
        weight=5.0,
        damage=20,
        clip_size=10,
        crit_damage=12,
        crit_multiplier=2.0,
        equipment_slot=1,
        enchantment_form_id=None,
        is_playable=True,
    )
    backup = Weapon(
        form_id=0xE002,
        editor_id="BackupWeapon",
        name="Backup",
        value=10,
        health=100,
        weight=5.0,
        damage=18,
        clip_size=10,
        crit_damage=30,
        crit_multiplier=0.0,
        equipment_slot=2,
        enchantment_form_id=None,
        is_playable=True,
    )
    c.equipment[1] = primary.form_id
    c.equipment[2] = backup.form_id

    stats = compute_stats(
        c,
        GameSettings.defaults(),
        armors={},
        weapons={primary.form_id: primary, backup.form_id: backup},
    )

    # max(12*2.0, 30*1.0) = 30.0
    assert stats.crit_damage_potential == pytest.approx(30.0)


# --- Integration test: equipment from real ESM ---

pytestmark_esm = pytest.mark.skipif(
    not ESM_PATH.exists(), reason="FalloutNV.esm not found"
)


@pytest.fixture(scope="module")
def esm_data():
    return ESM_PATH.read_bytes()


@pytest.fixture(scope="module")
def resolved_armors(esm_data):
    """Parse and resolve all armors from the ESM."""
    from fnv_planner.parser.effect_resolver import EffectResolver
    from fnv_planner.parser.item_parser import parse_all_armors

    resolver = EffectResolver.from_esm(esm_data)
    armors = parse_all_armors(esm_data)
    for a in armors:
        resolver.resolve_armor(a)
    return {a.form_id: a for a in armors}


@pytest.fixture(scope="module")
def armor_by_edid(resolved_armors):
    return {a.editor_id: a for a in resolved_armors.values()}


@pytestmark_esm
def test_lucky_shades_flow(resolved_armors, armor_by_edid):
    """Equip Lucky Shades, verify +1 Luck and +3 Perception flow through."""
    shades = armor_by_edid["UniqueGlassesLuckyShades"]

    c = Character()
    c.equipment[0] = shades.form_id

    gmst = GameSettings.defaults()
    stats = compute_stats(c, gmst, armors=resolved_armors)

    # Effective SPECIAL should show the bonuses
    assert stats.effective_special[AV.LUCK] == 6    # 5 + 1
    assert stats.effective_special[AV.PERCEPTION] == 8  # 5 + 3

    # Crit chance should reflect Luck 6: 0 + 6*1 = 6
    assert stats.crit_chance == pytest.approx(6.0)

    # Perception-governed skills should be higher:
    # Lockpick with PER 8: 2 + 8*2 + ceil(6*0.5) = 2 + 16 + 3 = 21
    assert stats.skills[AV.LOCKPICK] == 21
