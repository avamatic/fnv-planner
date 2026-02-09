"""Tests for the perk dependency graph.

Unit tests use synthetic Perk objects — no ESM required.
Integration tests parse the real FalloutNV.esm and are skipped if absent.
"""

from pathlib import Path

import pytest

from fnv_planner.graph.dependency_graph import (
    DependencyGraph,
    RequirementClause,
    RequirementSet,
    _build_clauses_from_reqs,
    _compare,
    _evaluate_requirement_set,
)
from fnv_planner.models.character import Character
from fnv_planner.models.constants import ActorValue
from fnv_planner.models.derived_stats import CharacterStats, compute_stats
from fnv_planner.models.game_settings import GameSettings
from fnv_planner.models.perk import (
    LevelRequirement,
    Perk,
    PerkRequirement,
    SexRequirement,
    SkillRequirement,
)


AV = ActorValue

ESM_PATH = Path(
    "/home/am/.local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm"
)


# ---------------------------------------------------------------------------
# Helpers — minimal Perk construction
# ---------------------------------------------------------------------------


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
    sex_requirement: SexRequirement | None = None,
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
        sex_requirement=sex_requirement,
        level_requirements=level_requirements or [],
    )


def _default_stats(**overrides: int) -> CharacterStats:
    """CharacterStats with all SPECIAL=5, all skills=15 by default."""
    special = {av: 5 for av in range(AV.STRENGTH, AV.LUCK + 1)}
    skills = {av: 15 for av in range(AV.BARTER, AV.UNARMED + 1)}
    for k, v in overrides.items():
        # Accept "strength", "guns", etc.
        av = getattr(AV, k.upper(), None)
        if av is not None:
            if av in special:
                special[av] = v
            elif av in skills:
                skills[av] = v
    return CharacterStats(effective_special=special, skills=skills)


# ===========================================================================
# Unit tests — OR-group building
# ===========================================================================


class TestBuildClauses:
    def test_empty(self):
        assert _build_clauses_from_reqs([]) == []

    def test_single_requirement(self):
        req = SkillRequirement(AV.STRENGTH, "Strength", ">=", 5)
        clauses = _build_clauses_from_reqs([req])
        assert len(clauses) == 1
        assert len(clauses[0].requirements) == 1

    def test_two_and_requirements(self):
        """Two reqs without is_or → two separate AND clauses."""
        a = SkillRequirement(AV.STRENGTH, "Strength", ">=", 5)
        b = SkillRequirement(AV.ENDURANCE, "Endurance", ">=", 5)
        clauses = _build_clauses_from_reqs([a, b])
        assert len(clauses) == 2
        assert len(clauses[0].requirements) == 1
        assert len(clauses[1].requirements) == 1

    def test_or_pair(self):
        """[A, B(or)] → one clause with two alternatives."""
        a = SkillRequirement(AV.MELEE_WEAPONS, "Melee Weapons", ">=", 70)
        b = SkillRequirement(AV.UNARMED, "Unarmed", ">=", 70, is_or=True)
        clauses = _build_clauses_from_reqs([a, b])
        assert len(clauses) == 1
        assert len(clauses[0].requirements) == 2

    def test_mixed_and_or(self):
        """[A, B(or), C] → [(A, B), (C,)] i.e. (A OR B) AND C."""
        a = SkillRequirement(AV.STRENGTH, "Strength", ">=", 5)
        b = SkillRequirement(AV.ENDURANCE, "Endurance", ">=", 5, is_or=True)
        c = SkillRequirement(AV.AGILITY, "Agility", ">=", 3)
        clauses = _build_clauses_from_reqs([a, b, c])
        assert len(clauses) == 2
        assert len(clauses[0].requirements) == 2  # A OR B
        assert len(clauses[1].requirements) == 1  # C

    def test_triple_or(self):
        """Three consecutive ORs → single clause with 3 alternatives."""
        a = SkillRequirement(AV.GUNS, "Guns", ">=", 50)
        b = SkillRequirement(AV.ENERGY_WEAPONS, "Energy Weapons", ">=", 50, is_or=True)
        c = SkillRequirement(AV.EXPLOSIVES, "Explosives", ">=", 50, is_or=True)
        clauses = _build_clauses_from_reqs([a, b, c])
        assert len(clauses) == 1
        assert len(clauses[0].requirements) == 3


# ===========================================================================
# Unit tests — _compare
# ===========================================================================


class TestCompare:
    def test_gte(self):
        assert _compare(5, ">=", 5) is True
        assert _compare(4, ">=", 5) is False

    def test_gt(self):
        assert _compare(6, ">", 5) is True
        assert _compare(5, ">", 5) is False

    def test_eq(self):
        assert _compare(5, "==", 5) is True
        assert _compare(6, "==", 5) is False

    def test_neq(self):
        assert _compare(6, "!=", 5) is True
        assert _compare(5, "!=", 5) is False

    def test_lt(self):
        assert _compare(4, "<", 5) is True
        assert _compare(5, "<", 5) is False

    def test_lte(self):
        assert _compare(5, "<=", 5) is True
        assert _compare(6, "<=", 5) is False

    def test_unknown_operator(self):
        assert _compare(5, "??", 5) is False


# ===========================================================================
# Unit tests — eligibility
# ===========================================================================


class TestEligibility:
    def test_no_requirements(self):
        """Perk with no requirements is available if level/rank allow."""
        perk = _perk(min_level=2)
        graph = DependencyGraph.build([perk])
        char = Character(level=2)
        stats = _default_stats()
        assert graph.can_take_perk(0x1000, char, stats)

    def test_special_met(self):
        perk = _perk(skill_requirements=[
            SkillRequirement(AV.STRENGTH, "Strength", ">=", 5),
        ])
        graph = DependencyGraph.build([perk])
        char = Character(level=2)
        stats = _default_stats(strength=5)
        assert graph.can_take_perk(0x1000, char, stats)

    def test_special_unmet(self):
        perk = _perk(skill_requirements=[
            SkillRequirement(AV.STRENGTH, "Strength", ">=", 7),
        ])
        graph = DependencyGraph.build([perk])
        char = Character(level=2)
        stats = _default_stats(strength=5)
        assert not graph.can_take_perk(0x1000, char, stats)

    def test_skill_met(self):
        perk = _perk(skill_requirements=[
            SkillRequirement(AV.GUNS, "Guns", ">=", 50),
        ])
        graph = DependencyGraph.build([perk])
        char = Character(level=2)
        stats = _default_stats(guns=50)
        assert graph.can_take_perk(0x1000, char, stats)

    def test_skill_unmet(self):
        perk = _perk(skill_requirements=[
            SkillRequirement(AV.GUNS, "Guns", ">=", 50),
        ])
        graph = DependencyGraph.build([perk])
        char = Character(level=2)
        stats = _default_stats(guns=30)
        assert not graph.can_take_perk(0x1000, char, stats)

    def test_or_group_first_alt_met(self):
        """OR group: first alternative satisfies."""
        perk = _perk(skill_requirements=[
            SkillRequirement(AV.MELEE_WEAPONS, "Melee Weapons", ">=", 70),
            SkillRequirement(AV.UNARMED, "Unarmed", ">=", 70, is_or=True),
        ])
        graph = DependencyGraph.build([perk])
        char = Character(level=2)
        stats = _default_stats(melee_weapons=80, unarmed=10)
        assert graph.can_take_perk(0x1000, char, stats)

    def test_or_group_second_alt_met(self):
        """OR group: second alternative satisfies."""
        perk = _perk(skill_requirements=[
            SkillRequirement(AV.MELEE_WEAPONS, "Melee Weapons", ">=", 70),
            SkillRequirement(AV.UNARMED, "Unarmed", ">=", 70, is_or=True),
        ])
        graph = DependencyGraph.build([perk])
        char = Character(level=2)
        stats = _default_stats(melee_weapons=10, unarmed=80)
        assert graph.can_take_perk(0x1000, char, stats)

    def test_or_group_neither_met(self):
        """OR group: neither alternative satisfies."""
        perk = _perk(skill_requirements=[
            SkillRequirement(AV.MELEE_WEAPONS, "Melee Weapons", ">=", 70),
            SkillRequirement(AV.UNARMED, "Unarmed", ">=", 70, is_or=True),
        ])
        graph = DependencyGraph.build([perk])
        char = Character(level=2)
        stats = _default_stats(melee_weapons=10, unarmed=10)
        assert not graph.can_take_perk(0x1000, char, stats)

    def test_perk_dep_met(self):
        """Perk prerequisite satisfied by having it in perks dict."""
        prereq = _perk(form_id=0x2000, editor_id="PrereqPerk", name="Prereq")
        perk = _perk(
            form_id=0x3000,
            perk_requirements=[PerkRequirement(0x2000, rank=1)],
        )
        graph = DependencyGraph.build([prereq, perk])
        char = Character(level=2, perks={2: [0x2000]})
        stats = _default_stats()
        assert graph.can_take_perk(0x3000, char, stats)

    def test_perk_dep_unmet(self):
        prereq = _perk(form_id=0x2000, editor_id="PrereqPerk", name="Prereq")
        perk = _perk(
            form_id=0x3000,
            perk_requirements=[PerkRequirement(0x2000, rank=1)],
        )
        graph = DependencyGraph.build([prereq, perk])
        char = Character(level=2)
        stats = _default_stats()
        assert not graph.can_take_perk(0x3000, char, stats)

    def test_level_requirement(self):
        perk = _perk(min_level=8)
        graph = DependencyGraph.build([perk])
        stats = _default_stats()
        assert not graph.can_take_perk(0x1000, Character(level=5), stats)
        assert graph.can_take_perk(0x1000, Character(level=8), stats)

    def test_level_requirement_ctda(self):
        """LevelRequirement from CTDA (e.g. GetLevel < 30 for Here and Now)."""
        perk = _perk(
            min_level=2,
            level_requirements=[LevelRequirement("<", 30)],
        )
        graph = DependencyGraph.build([perk])
        stats = _default_stats()
        assert graph.can_take_perk(0x1000, Character(level=10), stats)
        assert not graph.can_take_perk(0x1000, Character(level=30), stats)

    def test_max_rank_reached(self):
        """Can't take a perk if already at max rank."""
        perk = _perk(ranks=1)
        graph = DependencyGraph.build([perk])
        char = Character(level=2, perks={2: [0x1000]})
        stats = _default_stats()
        assert not graph.can_take_perk(0x1000, char, stats)

    def test_multi_rank_perk(self):
        """Multi-rank perk: can take rank 2 if already have rank 1."""
        perk = _perk(ranks=3)
        graph = DependencyGraph.build([perk])
        stats = _default_stats()
        # 0 ranks taken — can take
        assert graph.can_take_perk(0x1000, Character(level=2), stats)
        # 1 rank taken — can take rank 2
        char = Character(level=2, perks={2: [0x1000]})
        assert graph.can_take_perk(0x1000, char, stats)
        # 3 ranks taken — maxed out
        char = Character(level=2, perks={2: [0x1000, 0x1000, 0x1000]})
        assert not graph.can_take_perk(0x1000, char, stats)

    def test_traits_excluded(self):
        """Traits are not offered as level-up perks."""
        perk = _perk(is_trait=True, min_level=1)
        graph = DependencyGraph.build([perk])
        char = Character(level=1)
        stats = _default_stats()
        assert not graph.can_take_perk(0x1000, char, stats)

    def test_non_playable_excluded(self):
        """Non-playable perks can never be taken."""
        perk = _perk(is_playable=False)
        graph = DependencyGraph.build([perk])
        char = Character(level=2)
        stats = _default_stats()
        assert not graph.can_take_perk(0x1000, char, stats)

    def test_equipment_bonus_pushes_over_threshold(self):
        """Equipment bonuses in effective stats can meet requirements."""
        perk = _perk(skill_requirements=[
            SkillRequirement(AV.STRENGTH, "Strength", ">=", 8),
        ])
        graph = DependencyGraph.build([perk])
        char = Character(level=2)
        # Base 5, equipment pushes to 8
        stats = _default_stats(strength=8)
        assert graph.can_take_perk(0x1000, char, stats)

    def test_sex_requirement_met(self):
        perk = _perk(sex_requirement=SexRequirement(sex=0))  # Male
        graph = DependencyGraph.build([perk])
        char = Character(level=2, sex=0)
        stats = _default_stats()
        assert graph.can_take_perk(0x1000, char, stats)

    def test_sex_requirement_unmet(self):
        perk = _perk(sex_requirement=SexRequirement(sex=0))  # Male
        graph = DependencyGraph.build([perk])
        char = Character(level=2, sex=1)
        stats = _default_stats()
        assert not graph.can_take_perk(0x1000, char, stats)

    def test_sex_requirement_unset(self):
        """If sex is None, sex requirements cannot be satisfied."""
        perk = _perk(sex_requirement=SexRequirement(sex=0))
        graph = DependencyGraph.build([perk])
        char = Character(level=2)  # sex=None
        stats = _default_stats()
        assert not graph.can_take_perk(0x1000, char, stats)

    def test_perk_dep_in_traits(self):
        """Perk prerequisite satisfied by having it as a trait."""
        prereq = _perk(form_id=0x2000, editor_id="TraitPerk", is_trait=True, min_level=1)
        perk = _perk(
            form_id=0x3000,
            perk_requirements=[PerkRequirement(0x2000, rank=1)],
        )
        graph = DependencyGraph.build([prereq, perk])
        char = Character(level=2, traits=[0x2000])
        stats = _default_stats()
        assert graph.can_take_perk(0x3000, char, stats)


# ===========================================================================
# Unit tests — graph queries
# ===========================================================================


class TestGraphQueries:
    def _build_chain(self):
        """Build A → B → C chain (C requires B, B requires A)."""
        a = _perk(form_id=0xA, editor_id="A", name="A", min_level=2)
        b = _perk(
            form_id=0xB, editor_id="B", name="B", min_level=4,
            perk_requirements=[PerkRequirement(0xA, rank=1)],
        )
        c = _perk(
            form_id=0xC, editor_id="C", name="C", min_level=6,
            perk_requirements=[PerkRequirement(0xB, rank=1)],
        )
        return DependencyGraph.build([a, b, c])

    def test_available_perks(self):
        """Only perks whose requirements are met should appear."""
        easy = _perk(form_id=0x1, editor_id="Easy", min_level=2)
        hard = _perk(
            form_id=0x2, editor_id="Hard", min_level=2,
            skill_requirements=[
                SkillRequirement(AV.STRENGTH, "Strength", ">=", 10),
            ],
        )
        graph = DependencyGraph.build([easy, hard])
        char = Character(level=2)
        stats = _default_stats(strength=5)
        available = graph.available_perks(char, stats)
        assert 0x1 in available
        assert 0x2 not in available

    def test_perk_chain(self):
        """perk_chain(C) → [A, B] (transitive deps, deepest first)."""
        graph = self._build_chain()
        chain = graph.perk_chain(0xC)
        assert chain == [0xA, 0xB]

    def test_perk_chain_no_deps(self):
        """Perk with no dependencies → empty chain."""
        graph = self._build_chain()
        chain = graph.perk_chain(0xA)
        assert chain == []

    def test_topological_order(self):
        """Every perk appears after its dependencies in topological order."""
        graph = self._build_chain()
        order = graph.topological_order()
        idx = {pid: i for i, pid in enumerate(order)}
        # A before B, B before C
        assert idx[0xA] < idx[0xB]
        assert idx[0xB] < idx[0xC]

    def test_dependents_of(self):
        graph = self._build_chain()
        assert graph.dependents_of(0xA) == [0xB]
        assert graph.dependents_of(0xB) == [0xC]
        assert graph.dependents_of(0xC) == []

    def test_available_traits(self):
        trait = _perk(form_id=0x10, editor_id="Trait1", is_trait=True, min_level=1)
        perk = _perk(form_id=0x20, editor_id="Perk1", min_level=2)
        graph = DependencyGraph.build([trait, perk])
        traits = graph.available_traits()
        assert 0x10 in traits
        assert 0x20 not in traits

    def test_get_node(self):
        perk = _perk(form_id=0x42)
        graph = DependencyGraph.build([perk])
        node = graph.get_node(0x42)
        assert node is not None
        assert node.perk_id == 0x42

    def test_get_node_unknown(self):
        graph = DependencyGraph.build([])
        assert graph.get_node(0x9999) is None


# ===========================================================================
# Unit tests — unmet_requirements
# ===========================================================================


class TestUnmetRequirements:
    def test_all_met(self):
        perk = _perk(min_level=2)
        graph = DependencyGraph.build([perk])
        char = Character(level=2)
        stats = _default_stats()
        assert graph.unmet_requirements(0x1000, char, stats) == []

    def test_single_unmet(self):
        perk = _perk(skill_requirements=[
            SkillRequirement(AV.STRENGTH, "Strength", ">=", 8),
        ])
        graph = DependencyGraph.build([perk])
        char = Character(level=2)
        stats = _default_stats(strength=5)
        unmet = graph.unmet_requirements(0x1000, char, stats)
        assert len(unmet) == 1
        assert "Strength >= 8" in unmet[0]

    def test_or_group_unmet(self):
        perk = _perk(skill_requirements=[
            SkillRequirement(AV.MELEE_WEAPONS, "Melee Weapons", ">=", 70),
            SkillRequirement(AV.UNARMED, "Unarmed", ">=", 70, is_or=True),
        ])
        graph = DependencyGraph.build([perk])
        char = Character(level=2)
        stats = _default_stats()
        unmet = graph.unmet_requirements(0x1000, char, stats)
        assert len(unmet) == 1
        assert "One of:" in unmet[0]
        assert "OR" in unmet[0]

    def test_level_unmet(self):
        perk = _perk(min_level=10)
        graph = DependencyGraph.build([perk])
        char = Character(level=5)
        stats = _default_stats()
        unmet = graph.unmet_requirements(0x1000, char, stats)
        assert any("Level >= 10" in u for u in unmet)

    def test_max_rank_unmet(self):
        perk = _perk(ranks=1)
        graph = DependencyGraph.build([perk])
        char = Character(level=2, perks={2: [0x1000]})
        stats = _default_stats()
        unmet = graph.unmet_requirements(0x1000, char, stats)
        assert any("max rank" in u for u in unmet)

    def test_unknown_perk(self):
        graph = DependencyGraph.build([])
        unmet = graph.unmet_requirements(0x9999, Character(), _default_stats())
        assert len(unmet) == 1
        assert "Unknown" in unmet[0]


# ===========================================================================
# Unit tests — edge cases
# ===========================================================================


class TestEdgeCases:
    def test_unknown_perk_id_can_take(self):
        graph = DependencyGraph.build([])
        assert not graph.can_take_perk(0x9999, Character(level=50), _default_stats())

    def test_prerequisites_for_unknown(self):
        graph = DependencyGraph.build([])
        assert graph.prerequisites_for(0x9999) is None

    def test_prerequisites_for_known(self):
        perk = _perk(skill_requirements=[
            SkillRequirement(AV.STRENGTH, "Strength", ">=", 5),
        ])
        graph = DependencyGraph.build([perk])
        rs = graph.prerequisites_for(0x1000)
        assert rs is not None
        assert len(rs.clauses) == 1


# ===========================================================================
# Integration tests — real ESM
# ===========================================================================


pytestmark_esm = pytest.mark.skipif(
    not ESM_PATH.exists(), reason="FalloutNV.esm not found"
)


@pytest.fixture(scope="module")
def esm_perks():
    data = ESM_PATH.read_bytes()
    from fnv_planner.parser.perk_parser import parse_all_perks
    return parse_all_perks(data)


@pytest.fixture(scope="module")
def esm_graph(esm_perks):
    return DependencyGraph.build(esm_perks)


@pytest.fixture(scope="module")
def perk_by_edid(esm_perks):
    return {p.editor_id: p for p in esm_perks}


@pytestmark_esm
def test_trait_count(esm_graph):
    """Should find exactly 10 playable traits in vanilla FNV."""
    traits = esm_graph.available_traits()
    assert len(traits) == 10


@pytestmark_esm
def test_level1_few_perks_available(esm_graph):
    """Default level-1 character: only challenge perks (min_level=0) are available."""
    char = Character(level=1)
    gmst = GameSettings.defaults()
    stats = compute_stats(char, gmst)
    available = esm_graph.available_perks(char, stats)
    # Challenge perks like "Bug Stomper" and "Set Lasers for Fun" have
    # min_level=0, no stat requirements — they're unlocked via challenges.
    for pid in available:
        node = esm_graph.get_node(pid)
        assert node is not None
        assert node.min_level == 0


@pytestmark_esm
def test_educated_requirements(esm_graph, perk_by_edid):
    """Educated: unavailable at level 1 / INT 3; available at level 4 / INT 4."""
    educated = perk_by_edid["Educated"]
    gmst = GameSettings.defaults()

    # Level 1, INT 3 → no
    char = Character(level=1)
    char.special[AV.INTELLIGENCE] = 3
    stats = compute_stats(char, gmst)
    assert not esm_graph.can_take_perk(educated.form_id, char, stats)

    # Level 4, INT 4 → yes
    char = Character(level=4)
    char.special[AV.INTELLIGENCE] = 4
    stats = compute_stats(char, gmst)
    assert esm_graph.can_take_perk(educated.form_id, char, stats)


@pytestmark_esm
def test_strong_back_and_clauses(esm_graph, perk_by_edid):
    """Strong Back: two AND-clauses (STR >= 5 AND END >= 5)."""
    sb = perk_by_edid["StrongBack"]
    gmst = GameSettings.defaults()

    # STR 5 END 5 level 8 → yes
    char = Character(level=8)
    stats = compute_stats(char, gmst)
    assert esm_graph.can_take_perk(sb.form_id, char, stats)

    # STR 3 → no
    char = Character(level=8)
    char.special[AV.STRENGTH] = 3
    stats = compute_stats(char, gmst)
    assert not esm_graph.can_take_perk(sb.form_id, char, stats)


@pytestmark_esm
def test_piercing_strike_unarmed_req(esm_graph, perk_by_edid):
    """Piercing Strike: requires Unarmed >= 70.

    The ESM has is_or=True on the sole skill requirement (no preceding req
    to OR with), so it becomes a single-element clause.
    """
    ps = perk_by_edid["PiercingStrike"]
    node = esm_graph.get_node(ps.form_id)
    assert node is not None

    # Should have at least one clause with a skill requirement for Unarmed
    skill_clauses = [
        c for c in node.requirements.clauses
        if any(isinstance(r, SkillRequirement) for r in c.requirements)
    ]
    assert len(skill_clauses) >= 1
    # The Unarmed requirement should be present
    all_reqs = [r for c in skill_clauses for r in c.requirements]
    unarmed_reqs = [r for r in all_reqs if isinstance(r, SkillRequirement) and r.name == "Unarmed"]
    assert len(unarmed_reqs) == 1
    assert unarmed_reqs[0].value == 70


@pytestmark_esm
def test_topological_order_valid(esm_graph):
    """Every perk appears after its dependencies in topological order."""
    order = esm_graph.topological_order()
    idx = {pid: i for i, pid in enumerate(order)}

    for pid in order:
        node = esm_graph.get_node(pid)
        if node is None:
            continue
        for clause in node.requirements.clauses:
            for req in clause.requirements:
                if isinstance(req, PerkRequirement):
                    dep_id = req.perk_form_id
                    if dep_id in idx:
                        assert idx[dep_id] < idx[pid], (
                            f"Perk {pid:#x} appears before its dep {dep_id:#x}"
                        )
