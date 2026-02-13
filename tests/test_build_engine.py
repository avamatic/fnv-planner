"""Tests for the build engine.

Unit tests use synthetic data — no ESM required.
Integration tests parse the real FalloutNV.esm and are skipped if absent.
"""

from pathlib import Path

import pytest

from fnv_planner.engine.build_config import BuildConfig
from fnv_planner.engine.build_engine import (
    BuildEngine,
    BuildError,
    BuildState,
    LevelPlan,
)
from fnv_planner.graph.dependency_graph import DependencyGraph
from fnv_planner.models.character import Character
from fnv_planner.models.constants import ActorValue, SPECIAL_INDICES
from fnv_planner.models.derived_stats import CharacterStats, compute_stats
from fnv_planner.models.effect import StatEffect
from fnv_planner.models.game_settings import GameSettings
from fnv_planner.models.item import Armor
from fnv_planner.models.perk import (
    LevelRequirement,
    Perk,
    PerkRequirement,
    SkillRequirement,
)


AV = ActorValue

ESM_PATH = Path(
    "/home/am/.local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _special(
    st: int = 5, pe: int = 5, en: int = 5,
    ch: int = 5, in_: int = 5, ag: int = 5, lk: int = 5,
) -> dict[int, int]:
    """Build a SPECIAL dict. Caller must ensure sum equals the budget (40)."""
    return {
        AV.STRENGTH: st, AV.PERCEPTION: pe, AV.ENDURANCE: en,
        AV.CHARISMA: ch, AV.INTELLIGENCE: in_, AV.AGILITY: ag,
        AV.LUCK: lk,
    }


def _balanced_special() -> dict[int, int]:
    """SPECIAL summing to 40 with INT=5, AG=5, LCK=4 (keeps skill calcs stable)."""
    return _special(st=7, pe=7, en=6, ch=6, in_=5, ag=5, lk=4)


def _perk(
    form_id: int = 0x1000,
    editor_id: str = "TestPerk",
    name: str = "Test Perk",
    min_level: int = 2,
    ranks: int = 1,
    is_playable: bool = True,
    is_trait: bool = False,
    skill_requirements: list[SkillRequirement] | None = None,
    perk_requirements: list[PerkRequirement] | None = None,
    level_requirements: list[LevelRequirement] | None = None,
) -> Perk:
    return Perk(
        form_id=form_id,
        editor_id=editor_id,
        name=name,
        description="",
        is_trait=is_trait,
        min_level=min_level,
        ranks=ranks,
        is_playable=is_playable,
        is_hidden=False,
        skill_requirements=skill_requirements or [],
        perk_requirements=perk_requirements or [],
        level_requirements=level_requirements or [],
    )


def _engine(
    perks: list[Perk] | None = None,
    config: BuildConfig | None = None,
) -> BuildEngine:
    """Create a BuildEngine with vanilla GMST and optional synthetic perks."""
    gmst = GameSettings.defaults()
    graph = DependencyGraph.build(perks or [])
    return BuildEngine(gmst, graph, config)


def _setup_creation(engine: BuildEngine) -> None:
    """Fill in creation-phase choices with sensible defaults."""
    engine.set_special(_balanced_special())
    engine.set_sex(0)
    engine.set_tagged_skills({AV.GUNS, AV.LOCKPICK, AV.SPEECH})


# ===========================================================================
# Creation validation
# ===========================================================================


class TestCreationSPECIAL:
    def test_valid_special(self):
        e = _engine()
        e.set_special(_balanced_special())
        # Should not raise

    def test_over_budget(self):
        e = _engine()
        with pytest.raises(ValueError, match="budget"):
            e.set_special(_special(st=10, pe=10, en=5, ch=5, in_=5, ag=5, lk=5))

    def test_under_budget(self):
        e = _engine()
        with pytest.raises(ValueError, match="budget"):
            e.set_special(_special(st=1, pe=1, en=1, ch=1, in_=1, ag=1, lk=1))

    def test_below_min(self):
        e = _engine()
        with pytest.raises(ValueError, match="out of range"):
            e.set_special(_special(st=0, pe=5, en=5, ch=5, in_=5, ag=5, lk=8))

    def test_above_max(self):
        e = _engine()
        with pytest.raises(ValueError, match="out of range"):
            e.set_special(_special(st=11, pe=5, en=5, ch=5, in_=5, ag=5, lk=2))

    def test_missing_stat(self):
        e = _engine()
        incomplete = {AV.STRENGTH: 5, AV.PERCEPTION: 5}
        with pytest.raises(ValueError, match="7 SPECIAL"):
            e.set_special(incomplete)


class TestCreationTags:
    def test_valid_tags(self):
        e = _engine()
        e.set_tagged_skills({AV.GUNS, AV.LOCKPICK, AV.SPEECH})

    def test_too_many(self):
        e = _engine()
        with pytest.raises(ValueError, match="exactly 3"):
            e.set_tagged_skills({AV.GUNS, AV.LOCKPICK, AV.SPEECH, AV.SCIENCE})

    def test_too_few(self):
        e = _engine()
        with pytest.raises(ValueError, match="exactly 3"):
            e.set_tagged_skills({AV.GUNS, AV.LOCKPICK})

    def test_invalid_av(self):
        e = _engine()
        with pytest.raises(ValueError, match="Invalid skill"):
            e.set_tagged_skills({AV.GUNS, AV.LOCKPICK, AV.STRENGTH})

    def test_big_guns_invalid_by_default(self):
        e = _engine()
        with pytest.raises(ValueError, match="Invalid skill"):
            e.set_tagged_skills({AV.GUNS, AV.LOCKPICK, AV.BIG_GUNS})

    def test_big_guns_valid_when_enabled(self):
        e = _engine(config=BuildConfig(include_big_guns=True))
        e.set_tagged_skills({AV.GUNS, AV.LOCKPICK, AV.BIG_GUNS})


class TestCreationTraits:
    def test_valid_traits(self):
        trait_a = _perk(form_id=0xA, is_trait=True, min_level=1)
        trait_b = _perk(form_id=0xB, is_trait=True, min_level=1)
        e = _engine(perks=[trait_a, trait_b])
        e.set_traits([0xA, 0xB])

    def test_zero_traits(self):
        e = _engine()
        e.set_traits([])  # Valid — traits are optional

    def test_too_many(self):
        traits = [
            _perk(form_id=i, editor_id=f"T{i}", is_trait=True, min_level=1)
            for i in range(0xA, 0xD)
        ]
        e = _engine(perks=traits)
        with pytest.raises(ValueError, match="At most 2"):
            e.set_traits([0xA, 0xB, 0xC])

    def test_invalid_trait(self):
        e = _engine()
        with pytest.raises(ValueError, match="not available"):
            e.set_traits([0xDEAD])

    def test_duplicate_traits(self):
        trait_a = _perk(form_id=0xA, is_trait=True, min_level=1)
        e = _engine(perks=[trait_a])
        with pytest.raises(ValueError, match="Duplicate"):
            e.set_traits([0xA, 0xA])


class TestCreationSex:
    def test_valid_male(self):
        e = _engine()
        e.set_sex(0)

    def test_valid_female(self):
        e = _engine()
        e.set_sex(1)

    def test_invalid(self):
        e = _engine()
        with pytest.raises(ValueError, match="0.*1"):
            e.set_sex(2)


# ===========================================================================
# Skill allocation
# ===========================================================================


class TestSkillAllocation:
    def _ready_engine(self, target: int = 3) -> BuildEngine:
        e = _engine()
        _setup_creation(e)
        e.set_target_level(target)
        return e

    def test_basic_allocation(self):
        e = self._ready_engine()
        # INT=5 → skill_points_per_level = 11 + floor(5*0.5) = 13
        e.allocate_skill_points(2, {AV.GUNS: 5, AV.SCIENCE: 8})

    def test_over_budget(self):
        e = self._ready_engine()
        with pytest.raises(ValueError, match="budget"):
            e.allocate_skill_points(2, {AV.GUNS: 14})  # Budget is 13

    def test_exact_budget(self):
        e = self._ready_engine()
        e.allocate_skill_points(2, {AV.GUNS: 13})

    def test_skill_cap_enforced(self):
        """Base skill + points cannot exceed skill_cap."""
        e = _engine(config=BuildConfig(skill_cap=30))
        _setup_creation(e)
        e.set_target_level(5)
        # Base Guns with AGI=5, LCK=4: initial = 2 + 5*2 + ceil(4*0.5) = 14
        # Tagged Guns: 14 + 15 = 29
        # Spending 2 more → 31 > cap 30
        with pytest.raises(ValueError, match="cap"):
            e.allocate_skill_points(2, {AV.GUNS: 2})

    def test_cumulative_across_levels(self):
        e = self._ready_engine(target=4)
        e.allocate_skill_points(2, {AV.GUNS: 5})
        e.allocate_skill_points(3, {AV.GUNS: 5})
        # Total spent on Guns: 10
        assert e.total_skill_points_spent(up_to_level=3) == 10

    def test_replace_allocation(self):
        e = self._ready_engine()
        e.allocate_skill_points(2, {AV.GUNS: 5})
        e.allocate_skill_points(2, {AV.SCIENCE: 3})
        # Replacement: previous Guns allocation gone.
        char = e.materialize(2)
        assert char.skill_points_spent.get(AV.GUNS, 0) == 0
        assert char.skill_points_spent.get(AV.SCIENCE, 0) == 3

    def test_invalid_skill_index(self):
        e = self._ready_engine()
        with pytest.raises(ValueError, match="Invalid skill"):
            e.allocate_skill_points(2, {AV.STRENGTH: 5})

    def test_level_1_rejected(self):
        e = self._ready_engine()
        with pytest.raises(ValueError, match="Cannot allocate"):
            e.allocate_skill_points(1, {AV.GUNS: 5})

    def test_big_guns_allocation_when_enabled(self):
        e = _engine(config=BuildConfig(include_big_guns=True))
        _setup_creation(e)
        e.set_tagged_skills({AV.GUNS, AV.LOCKPICK, AV.BIG_GUNS})
        e.set_target_level(3)
        e.allocate_skill_points(2, {AV.BIG_GUNS: 5})
        char = e.materialize(2)
        assert char.skill_points_spent[AV.BIG_GUNS] == 5


# ===========================================================================
# Perk selection
# ===========================================================================


class TestPerkSelection:
    def test_at_perk_level(self):
        perk = _perk(form_id=0x1000, min_level=2)
        e = _engine(perks=[perk])
        _setup_creation(e)
        e.set_target_level(4)
        e.select_perk(2, 0x1000)
        assert e._state.level_plans[2].perk == 0x1000

    def test_at_non_perk_level(self):
        perk = _perk(form_id=0x1000, min_level=2)
        e = _engine(perks=[perk])
        _setup_creation(e)
        e.set_target_level(4)
        with pytest.raises(ValueError, match="does not award"):
            e.select_perk(3, 0x1000)

    def test_ineligible_perk(self):
        perk = _perk(
            form_id=0x1000, min_level=2,
            skill_requirements=[
                SkillRequirement(AV.STRENGTH, "Strength", ">=", 10),
            ],
        )
        e = _engine(perks=[perk])
        _setup_creation(e)
        e.set_target_level(4)
        with pytest.raises(ValueError, match="not available"):
            e.select_perk(2, 0x1000)

    def test_remove_perk(self):
        perk = _perk(form_id=0x1000, min_level=2)
        e = _engine(perks=[perk])
        _setup_creation(e)
        e.set_target_level(4)
        e.select_perk(2, 0x1000)
        e.remove_perk(2)
        assert e._state.level_plans[2].perk is None

    def test_perk_with_skill_req(self):
        """Perk requiring Guns >= 30: tagged Guns starts at 29, need 1 point."""
        perk = _perk(
            form_id=0x2000, min_level=2,
            skill_requirements=[
                SkillRequirement(AV.GUNS, "Guns", ">=", 30),
            ],
        )
        e = _engine(perks=[perk])
        _setup_creation(e)
        e.set_target_level(4)
        # Guns base: 2 + 5*2 + ceil(4*0.5) = 14, + tag 15 = 29
        # Need 1 more point to meet >= 30
        e.allocate_skill_points(2, {AV.GUNS: 1})
        e.select_perk(2, 0x2000)

    def test_perk_chain(self):
        """Perk B requires Perk A — must take A before B."""
        perk_a = _perk(form_id=0xA, editor_id="A", name="A", min_level=2)
        perk_b = _perk(
            form_id=0xB, editor_id="B", name="B", min_level=4,
            perk_requirements=[PerkRequirement(0xA, rank=1)],
        )
        e = _engine(perks=[perk_a, perk_b])
        _setup_creation(e)
        e.set_target_level(6)

        # Can't take B at level 4 without A.
        with pytest.raises(ValueError, match="not available"):
            e.select_perk(4, 0xB)

        # Take A at level 2, then B at level 4.
        e.select_perk(2, 0xA)
        e.select_perk(4, 0xB)


# ===========================================================================
# Materialize / queries
# ===========================================================================


class TestQueries:
    def test_materialize_level_1(self):
        e = _engine()
        _setup_creation(e)
        char = e.materialize(1)
        assert char.level == 1
        assert char.special == _balanced_special()
        assert char.tagged_skills == {AV.GUNS, AV.LOCKPICK, AV.SPEECH}

    def test_materialize_mid_level(self):
        e = _engine()
        _setup_creation(e)
        e.set_target_level(5)
        e.allocate_skill_points(2, {AV.GUNS: 5})
        e.allocate_skill_points(3, {AV.GUNS: 3, AV.SCIENCE: 2})

        char = e.materialize(3)
        assert char.level == 3
        assert char.skill_points_spent[AV.GUNS] == 8
        assert char.skill_points_spent[AV.SCIENCE] == 2

        # At level 2, should only see level 2's allocation.
        char2 = e.materialize(2)
        assert char2.skill_points_spent[AV.GUNS] == 5
        assert AV.SCIENCE not in char2.skill_points_spent

    def test_stats_at(self):
        e = _engine()
        _setup_creation(e)
        stats = e.stats_at(1)
        assert isinstance(stats, CharacterStats)
        assert stats.max_level == 50

    def test_available_perks_at(self):
        easy = _perk(form_id=0x1, editor_id="Easy", min_level=2)
        hard = _perk(
            form_id=0x2, editor_id="Hard", min_level=2,
            skill_requirements=[
                SkillRequirement(AV.STRENGTH, "Strength", ">=", 10),
            ],
        )
        e = _engine(perks=[easy, hard])
        _setup_creation(e)
        e.set_target_level(4)

        available = e.available_perks_at(2)
        assert 0x1 in available
        assert 0x2 not in available

    def test_unspent_points(self):
        e = _engine()
        _setup_creation(e)
        e.set_target_level(3)
        # Budget at level 2: INT=5 → 13
        assert e.unspent_skill_points_at(2) == 13
        e.allocate_skill_points(2, {AV.GUNS: 5})
        assert e.unspent_skill_points_at(2) == 8

    def test_total_budget(self):
        e = _engine()
        _setup_creation(e)
        e.set_target_level(4)
        # INT=5 → 13 pts/level, levels 2-4 = 3 * 13 = 39
        assert e.total_skill_budget(up_to_level=4) == 39

    def test_is_perk_level(self):
        e = _engine()
        assert not e.is_perk_level(1)
        assert e.is_perk_level(2)
        assert not e.is_perk_level(3)
        assert e.is_perk_level(4)

    def test_perk_levels(self):
        e = _engine()
        e.set_target_level(10)
        assert e.perk_levels(up_to=10) == [2, 4, 6, 8, 10]

    def test_max_level(self):
        e = _engine()
        assert e.max_level == 50

    def test_materialize_includes_equipment_from_state(self):
        e = _engine()
        _setup_creation(e)
        e.set_equipment(slot=1, item_form_id=0xABCD)
        char = e.materialize(1)
        assert char.equipment == {1: 0xABCD}

    def test_stats_at_applies_equipment_effects_from_state(self):
        e = _engine()
        _setup_creation(e)
        armor = Armor(
            form_id=0x100,
            editor_id="ArmorStrength",
            name="Strength Armor",
            value=0,
            health=0,
            weight=0.0,
            damage_threshold=0.0,
            equipment_slot=0,
            enchantment_form_id=None,
            is_playable=True,
            stat_effects=[
                StatEffect(
                    actor_value=AV.STRENGTH,
                    actor_value_name="Strength",
                    magnitude=2.0,
                ),
            ],
        )
        e.set_equipment(slot=0, item_form_id=0x100)
        stats = e.stats_at(1, armors={0x100: armor})
        assert stats.effective_special[AV.STRENGTH] == _balanced_special()[AV.STRENGTH] + 2

    def test_set_equipment_bulk_replaces_existing_equipment(self):
        e = _engine()
        _setup_creation(e)
        e.set_equipment(slot=0, item_form_id=0x100)
        e.set_equipment(slot=1, item_form_id=0x101)
        e.set_equipment_bulk({2: 0x202})
        assert e.materialize(1).equipment == {2: 0x202}

    def test_set_equipment_bulk_invalidates_cache_once_for_all_changes(self):
        e = _engine()
        _setup_creation(e)
        # Prime cache.
        _ = e.stats_at(1)
        assert 1 in e._stats_cache
        # A single bulk replace should invalidate previously cached level 1 stats.
        e.set_equipment_bulk({0: 0x100, 1: 0x101, 2: 0x102})
        assert 1 not in e._stats_cache

    def test_state_property(self):
        e = _engine()
        _setup_creation(e)
        state = e.state
        assert isinstance(state, BuildState)
        assert state.special == _balanced_special()
        # Modifying returned state shouldn't affect engine.
        state.special[AV.STRENGTH] = 99
        assert e._state.special[AV.STRENGTH] != 99


# ===========================================================================
# Full simulation / validation
# ===========================================================================


class TestValidation:
    def test_validate_empty_build(self):
        e = _engine()
        errors = e.validate()
        # Should report missing SPECIAL, wrong tag count
        categories = {err.category for err in errors}
        assert "special" in categories
        assert "tags" in categories

    def test_validate_complete_creation(self):
        e = _engine()
        _setup_creation(e)
        errors = e.validate_creation()
        assert errors == []

    def test_validate_level_over_budget(self):
        e = _engine()
        _setup_creation(e)
        e.set_target_level(3)
        # Force an invalid plan by directly manipulating state.
        e._state.level_plans[2].skill_points = {AV.GUNS: 999}
        errors = e.validate_level(2)
        assert any(err.category == "skill_points" for err in errors)

    def test_validate_perk_at_non_perk_level(self):
        e = _engine()
        _setup_creation(e)
        e.set_target_level(4)
        # Force perk at non-perk level.
        e._state.level_plans[3].perk = 0xDEAD
        errors = e.validate_level(3)
        assert any(err.category == "perk" for err in errors)

    def test_is_valid_with_errors(self):
        e = _engine()
        assert not e.is_valid()

    def test_is_valid_clean(self):
        e = _engine()
        _setup_creation(e)
        # Level 1 only, no level-up plans needed.
        assert e.is_valid()

    def test_is_complete_level_1(self):
        """Level 1 only: complete if creation is valid."""
        e = _engine()
        _setup_creation(e)
        assert e.is_complete()

    def test_is_complete_with_levels(self):
        """Multi-level build: must spend all points + fill all perk slots."""
        perk = _perk(form_id=0x1000, min_level=2)
        e = _engine(perks=[perk])
        _setup_creation(e)
        e.set_target_level(3)

        assert not e.is_complete()  # Points unspent, perk unfilled

        # Spend all points at level 2 (budget=13) and level 3 (budget=13).
        e.allocate_skill_points(2, {AV.GUNS: 13})
        e.allocate_skill_points(3, {AV.GUNS: 13})
        e.select_perk(2, 0x1000)

        assert e.is_complete()


class TestFullSimulation:
    def test_level_1_to_10(self):
        """Build a character from level 1 to 10 with allocations and perks."""
        perk_a = _perk(form_id=0xA, editor_id="A", min_level=2)
        perk_b = _perk(form_id=0xB, editor_id="B", min_level=4)
        perk_c = _perk(form_id=0xC, editor_id="C", min_level=6)
        perk_d = _perk(form_id=0xD, editor_id="D", min_level=8)
        perk_e = _perk(form_id=0xE, editor_id="E", min_level=10)

        e = _engine(perks=[perk_a, perk_b, perk_c, perk_d, perk_e])
        _setup_creation(e)
        e.set_target_level(10)

        # Spread points across Guns then Lockpick to avoid hitting cap.
        skills_order = [AV.GUNS, AV.LOCKPICK, AV.SPEECH]
        for lv in range(2, 11):
            budget = e.unspent_skill_points_at(lv)
            remaining = budget
            allocation: dict[int, int] = {}
            cumulative = e._cumulative_skill_points(lv - 1)
            for skill in skills_order:
                if remaining <= 0:
                    break
                total = cumulative.get(skill, 0)
                base = e._base_skill(skill, total)
                headroom = 100 - base
                if headroom <= 0:
                    continue
                give = min(remaining, headroom)
                allocation[skill] = give
                remaining -= give
            e.allocate_skill_points(lv, allocation)

        # Select perks at even levels.
        e.select_perk(2, 0xA)
        e.select_perk(4, 0xB)
        e.select_perk(6, 0xC)
        e.select_perk(8, 0xD)
        e.select_perk(10, 0xE)

        assert e.is_complete()
        assert e.is_valid()

        # Check final character.
        char = e.materialize(10)
        assert char.level == 10
        assert len(char.perks) == 5
        total_pts = sum(char.skill_points_spent.values())
        assert total_pts == e.total_skill_budget(up_to_level=10)


# ===========================================================================
# BuildConfig variants
# ===========================================================================


class TestBuildConfig:
    def test_custom_perk_interval(self):
        """Perk every 3 levels instead of 2."""
        cfg = BuildConfig(perk_every_n_levels=3)
        e = _engine(config=cfg)
        e.set_target_level(10)
        assert e.perk_levels(up_to=10) == [3, 6, 9]

    def test_custom_skill_cap(self):
        """Lower skill cap blocks high investment."""
        cfg = BuildConfig(skill_cap=50)
        e = _engine(config=cfg)
        _setup_creation(e)
        e.set_target_level(10)

        # Guns tagged: base=29 (with LCK=4). Need 22 more to hit 51 > cap 50.
        # Spend 13 at level 2, then try 9 more at level 3 → total 22 → skill=51.
        e.allocate_skill_points(2, {AV.GUNS: 13})
        with pytest.raises(ValueError, match="cap"):
            e.allocate_skill_points(3, {AV.GUNS: 9})

    def test_custom_special_budget(self):
        """Custom SPECIAL budget (e.g. modded game with 45 points)."""
        cfg = BuildConfig(special_budget=45)
        e = _engine(config=cfg)

        # 40 points → too few for budget=45
        with pytest.raises(ValueError, match="budget"):
            e.set_special(_balanced_special())

        # 45 points → valid
        e.set_special(_special(st=7, pe=7, en=7, ch=7, in_=7, ag=5, lk=5))


# ===========================================================================
# Edge cases
# ===========================================================================


class TestEdgeCases:
    def test_reduce_target_level(self):
        e = _engine()
        _setup_creation(e)
        e.set_target_level(10)
        assert 10 in e._state.level_plans

        e.set_target_level(5)
        assert 10 not in e._state.level_plans
        assert 5 in e._state.level_plans
        assert e._state.target_level == 5

    def test_cache_invalidation(self):
        """Mutating a level should invalidate cached stats at that level and above."""
        e = _engine()
        _setup_creation(e)
        e.set_target_level(5)

        # Populate cache.
        _ = e.stats_at(3)
        _ = e.stats_at(4)
        assert 3 in e._stats_cache
        assert 4 in e._stats_cache

        # Mutate level 3 → should clear cache at 3 and above.
        e.allocate_skill_points(3, {AV.GUNS: 1})
        assert 3 not in e._stats_cache
        assert 4 not in e._stats_cache

    def test_state_round_trip(self):
        """Save state, restore with from_state, verify identical behaviour."""
        perk = _perk(form_id=0x1000, min_level=2)
        e1 = _engine(perks=[perk])
        _setup_creation(e1)
        e1.set_target_level(4)
        e1.allocate_skill_points(2, {AV.GUNS: 5})
        e1.select_perk(2, 0x1000)

        state = e1.state
        e2 = BuildEngine.from_state(
            state, GameSettings.defaults(), DependencyGraph.build([perk]),
        )

        # Materialized characters should match.
        c1 = e1.materialize(2)
        c2 = e2.materialize(2)
        assert c1.skill_points_spent == c2.skill_points_spent
        assert c1.perks == c2.perks
        assert c1.special == c2.special

    def test_copy(self):
        """Copied engine is independent of the original."""
        e = _engine()
        _setup_creation(e)
        e.set_target_level(5)

        clone = e.copy()
        clone.set_name("Clone")
        assert e._state.name != "Clone"

    def test_new_build_factory(self):
        gmst = GameSettings.defaults()
        graph = DependencyGraph.build([])
        e = BuildEngine.new_build(gmst, graph)
        assert e.max_level == 50

    def test_target_level_bounds(self):
        e = _engine()
        with pytest.raises(ValueError):
            e.set_target_level(0)
        with pytest.raises(ValueError):
            e.set_target_level(51)


# ===========================================================================
# Integration tests — real ESM
# ===========================================================================


pytestmark_esm = pytest.mark.skipif(
    not ESM_PATH.exists(), reason="FalloutNV.esm not found"
)


@pytest.fixture(scope="module")
def esm_data():
    return ESM_PATH.read_bytes()


@pytest.fixture(scope="module")
def esm_perks(esm_data):
    from fnv_planner.parser.perk_parser import parse_all_perks
    return parse_all_perks(esm_data)


@pytest.fixture(scope="module")
def esm_graph(esm_perks):
    return DependencyGraph.build(esm_perks)


@pytest.fixture(scope="module")
def esm_gmst(esm_data):
    return GameSettings.from_esm(esm_data)


@pytest.fixture(scope="module")
def perk_by_edid(esm_perks):
    return {p.editor_id: p for p in esm_perks}


@pytestmark_esm
def test_educated_via_engine(esm_gmst, esm_graph, perk_by_edid):
    """Educated selectable at level 4 with INT >= 4."""
    educated = perk_by_edid["Educated"]

    e = BuildEngine(esm_gmst, esm_graph)
    e.set_special(_special(st=6, pe=6, en=6, ch=6, in_=4, ag=6, lk=6))
    e.set_sex(0)
    e.set_tagged_skills({AV.GUNS, AV.LOCKPICK, AV.SPEECH})
    e.set_target_level(4)

    available = e.available_perks_at(4)
    assert educated.form_id in available
    e.select_perk(4, educated.form_id)


@pytestmark_esm
def test_strong_back_via_engine(esm_gmst, esm_graph, perk_by_edid):
    """Strong Back selectable at level 8 with STR >= 5 + END >= 5."""
    sb = perk_by_edid["StrongBack"]

    e = BuildEngine(esm_gmst, esm_graph)
    e.set_special(_special(st=6, pe=6, en=6, ch=6, in_=5, ag=5, lk=6))
    e.set_sex(0)
    e.set_tagged_skills({AV.GUNS, AV.LOCKPICK, AV.SPEECH})
    e.set_target_level(8)

    available = e.available_perks_at(8)
    assert sb.form_id in available
    e.select_perk(8, sb.form_id)


@pytestmark_esm
def test_trait_selection_from_esm(esm_gmst, esm_graph):
    """Traits from real ESM data can be selected via the engine."""
    e = BuildEngine(esm_gmst, esm_graph)
    traits = esm_graph.available_traits()
    assert len(traits) >= 2
    e.set_traits(traits[:2])


@pytestmark_esm
def test_full_build_to_max(esm_gmst, esm_graph):
    """Build to max level, validate clean (no perk selection, just points)."""
    e = BuildEngine(esm_gmst, esm_graph)
    e.set_special(_special(st=5, pe=5, en=5, ch=5, in_=9, ag=5, lk=6))
    e.set_sex(0)
    e.set_tagged_skills({AV.GUNS, AV.LOCKPICK, AV.SPEECH})
    max_lv = e.max_level
    e.set_target_level(max_lv)

    # Allocate all skill points, distributing across skills to respect cap.
    for lv in range(2, max_lv + 1):
        budget = e.unspent_skill_points_at(lv)
        remaining = budget
        allocation: dict[int, int] = {}
        for skill in [AV.GUNS, AV.LOCKPICK, AV.SPEECH, AV.SCIENCE,
                      AV.REPAIR, AV.MEDICINE, AV.SNEAK, AV.BARTER,
                      AV.EXPLOSIVES, AV.SURVIVAL, AV.MELEE_WEAPONS,
                      AV.UNARMED, AV.ENERGY_WEAPONS]:
            if remaining <= 0:
                break
            cumulative = e._cumulative_skill_points(lv - 1)
            total = cumulative.get(skill, 0)
            base = e._base_skill(skill, total)
            headroom = 100 - base
            if headroom <= 0:
                continue
            give = min(remaining, headroom)
            allocation[skill] = give
            remaining -= give
        if allocation:
            e.allocate_skill_points(lv, allocation)

    errors = e.validate()
    assert errors == [], f"Validation errors: {errors}"
