"""Tests for perk_parser — integration tests against real ESM data.

Verifies specific well-known perks and overall counts.
"""

from pathlib import Path

import pytest

from fnv_planner.parser.perk_parser import parse_all_perks


ESM_PATH = Path(
    "/home/am/.local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm"
)

pytestmark = pytest.mark.skipif(
    not ESM_PATH.exists(), reason="FalloutNV.esm not found"
)


@pytest.fixture(scope="module")
def perks():
    """Parse all perks once for the whole test module."""
    data = ESM_PATH.read_bytes()
    return parse_all_perks(data)


@pytest.fixture(scope="module")
def perk_by_edid(perks):
    """Index perks by editor ID for easy lookup."""
    return {p.editor_id: p for p in perks}


# --- Count tests ---

def test_total_perk_count(perks):
    assert len(perks) == 176


def test_playable_count(perks):
    playable = [p for p in perks if p.is_playable]
    assert len(playable) == 98


def test_trait_count(perks):
    traits = [p for p in perks if p.is_trait]
    assert len(traits) == 10


# --- Specific perk tests ---

def test_educated(perk_by_edid):
    """Educated: Intelligence >= 4, level 4, playable."""
    p = perk_by_edid["Educated"]
    assert p.name == "Educated"
    assert p.min_level == 4
    assert p.is_playable
    assert not p.is_trait
    assert p.ranks == 1

    # Requires Intelligence >= 4
    assert len(p.skill_requirements) == 1
    req = p.skill_requirements[0]
    assert req.name == "Intelligence"
    assert req.operator == ">="
    assert req.value == 4
    assert len(p.entry_point_effects) >= 1
    assert any(
        b.entry_point == 2 and any(len(payload) == 3 and payload[0] == 10 for payload in b.data_payloads)
        for b in p.entry_point_effects
    )


def test_strong_back(perk_by_edid):
    """Strong Back: Strength >= 5, Endurance >= 5, level 8."""
    p = perk_by_edid["StrongBack"]
    assert p.name == "Strong Back"
    assert p.min_level == 8
    assert p.is_playable

    assert len(p.skill_requirements) == 2
    reqs = {r.name: r for r in p.skill_requirements}
    assert "Strength" in reqs
    assert reqs["Strength"].value == 5
    assert reqs["Strength"].operator == ">="
    assert "Endurance" in reqs
    assert reqs["Endurance"].value == 5


def test_lady_killer(perk_by_edid):
    """Lady Killer: Must be Male, level 2."""
    p = perk_by_edid["LadyKiller"]
    assert p.name == "Lady Killer"
    assert p.min_level == 2
    assert p.is_playable

    assert p.sex_requirement is not None
    assert p.sex_requirement.sex == 0  # Male
    assert p.sex_requirement.name == "Male"


def test_wild_wasteland(perk_by_edid):
    """Wild Wasteland: trait, no skill requirements."""
    p = perk_by_edid["WildWasteland"]
    assert p.name == "Wild Wasteland"
    assert p.is_trait
    assert p.is_playable
    assert p.min_level == 1

    # No requirements (traits don't have stat requirements)
    assert len(p.skill_requirements) == 0
    assert p.sex_requirement is None


def test_splash_damage(perk_by_edid):
    """Splash Damage: Explosives >= 70, level 12."""
    p = perk_by_edid["SplashDamage"]
    assert p.name == "Splash Damage"
    assert p.min_level == 12
    assert p.is_playable

    assert len(p.skill_requirements) == 1
    req = p.skill_requirements[0]
    assert req.name == "Explosives"
    assert req.operator == ">="
    assert req.value == 70


def test_stonewall(perk_by_edid):
    """Stonewall: Endurance >= 6, Strength >= 6, level 8."""
    p = perk_by_edid["Stonewall"]
    assert p.name == "Stonewall"
    assert p.min_level == 8

    assert len(p.skill_requirements) == 2
    reqs = {r.name: r for r in p.skill_requirements}
    assert reqs["Endurance"].value == 6
    assert reqs["Strength"].value == 6


def test_or_flag_piercing_strike(perk_by_edid):
    """Piercing Strike has an OR flag on its Unarmed requirement."""
    p = perk_by_edid["PiercingStrike"]
    # Should have at least one OR requirement
    or_reqs = [r for r in p.skill_requirements if r.is_or]
    assert len(or_reqs) >= 1


def test_here_and_now(perk_by_edid):
    """Here and Now: GetLevel < 30 requirement."""
    p = perk_by_edid["HereandNow"]
    assert len(p.level_requirements) == 1
    req = p.level_requirements[0]
    assert req.operator == "<"
    assert req.value == 30


def test_comprehension_has_entry_point_effect(perk_by_edid):
    p = perk_by_edid["Comprehension"]
    assert len(p.entry_point_effects) >= 1
    assert any(
        b.entry_point == 2 and any(len(payload) == 3 and payload[0] == 11 for payload in b.data_payloads)
        for b in p.entry_point_effects
    )


def test_intense_training_has_ranked_special_effects(perk_by_edid):
    p = perk_by_edid["IntenseTraining"]
    # 10 ranked PRKE effect blocks for selectable SPECIAL increases.
    assert len([b for b in p.entry_point_effects if b.entry_point == 0]) >= 10


def test_ghastly_scavenger(perk_by_edid):
    """Ghastly Scavenger: has a GetIsReference raw condition (quest/NPC check)."""
    p = perk_by_edid["GhastlyScavenger"]
    assert len(p.raw_conditions) >= 1
    # Function 449 = GetIsReference
    assert any(c.function == 449 for c in p.raw_conditions)


def test_action_boy_sex_requirement(perk_by_edid):
    """Action Boy requires Male (sex=0)."""
    p = perk_by_edid["ActionBoy"]
    assert p.sex_requirement is not None
    assert p.sex_requirement.sex == 0


def test_action_girl_sex_requirement(perk_by_edid):
    """Action Girl requires Female (sex=1)."""
    p = perk_by_edid["ActionGirl"]
    assert p.sex_requirement is not None
    assert p.sex_requirement.sex == 1


def test_all_playable_have_names(perks):
    """Every playable perk should have a display name."""
    for p in perks:
        if p.is_playable:
            assert p.name, f"Playable perk {p.editor_id} has no name"
