"""Tests for UI-facing BuildUiModel adapter."""

from fnv_planner.engine.build_engine import BuildEngine
from fnv_planner.engine.ui_model import BuildUiModel
from fnv_planner.graph.dependency_graph import DependencyGraph
from fnv_planner.models.constants import ActorValue
from fnv_planner.models.effect import StatEffect
from fnv_planner.models.game_settings import GameSettings
from fnv_planner.models.item import Armor, Weapon
from fnv_planner.models.perk import Perk, RawCondition


AV = ActorValue


def _perk(
    form_id: int,
    is_trait: bool = False,
    min_level: int = 1,
) -> Perk:
    return Perk(
        form_id=form_id,
        editor_id=f"P{form_id:x}",
        name=f"Perk {form_id:x}",
        description="",
        is_trait=is_trait,
        min_level=min_level,
        ranks=1,
        is_playable=True,
        is_hidden=False,
    )


def _engine() -> BuildEngine:
    graph = DependencyGraph.build([
        _perk(0x1000, min_level=2),
        _perk(0x2000, is_trait=True, min_level=1),
    ])
    engine = BuildEngine(GameSettings.defaults(), graph)
    engine.set_special({
        AV.STRENGTH: 7,
        AV.PERCEPTION: 7,
        AV.ENDURANCE: 6,
        AV.CHARISMA: 6,
        AV.INTELLIGENCE: 5,
        AV.AGILITY: 5,
        AV.LUCK: 4,
    })
    engine.set_sex(0)
    engine.set_tagged_skills({AV.GUNS, AV.LOCKPICK, AV.SPEECH})
    engine.set_traits([0x2000])
    engine.set_target_level(4)
    engine.allocate_skill_points(2, {AV.GUNS: 5})
    engine.select_perk(2, 0x1000)
    return engine


def test_selected_entities_and_search_remove():
    engine = _engine()
    armor = Armor(
        form_id=0xAA,
        editor_id="ArmorAA",
        name="Metal Armor",
        value=20,
        health=100,
        weight=15.0,
        damage_threshold=6.0,
        equipment_slot=5,
        enchantment_form_id=None,
        is_playable=True,
    )
    weapon = Weapon(
        form_id=0xBB,
        editor_id="WeaponBB",
        name="Service Rifle",
        value=35,
        health=120,
        weight=8.0,
        damage=18,
        clip_size=24,
        crit_damage=10,
        crit_multiplier=1.0,
        equipment_slot=5,
        enchantment_form_id=None,
        is_playable=True,
    )
    engine.set_equipment(5, 0xAA)

    ui = BuildUiModel(engine, armors={0xAA: armor}, weapons={0xBB: weapon})
    selected = ui.selected_entities()
    assert any(e.kind == "trait" for e in selected)
    assert any(e.kind == "perk" and e.level == 2 for e in selected)
    assert any(e.kind == "equipment" and "Metal Armor" in e.label for e in selected)

    found = ui.search_selected_entities("metal")
    assert len(found) == 1
    assert found[0].kind == "equipment"

    assert ui.remove_selected_entity(found[0])
    assert engine.state.equipment == {}


def test_progression_and_compare_levels():
    engine = _engine()
    ui = BuildUiModel(engine)
    snapshots = ui.progression(1, 4)
    assert [s.level for s in snapshots] == [1, 2, 3, 4]
    assert snapshots[1].perk_id == 0x1000
    assert snapshots[1].spent_skill_points == 5

    cmp = ui.compare_levels(1, 4)
    assert cmp.from_level == 1
    assert cmp.to_level == 4
    assert cmp.stat_deltas["hit_points"] > 0
    assert "crit_damage_potential" in cmp.stat_deltas
    assert cmp.skill_deltas[AV.GUNS] >= 5


def test_gear_catalog_and_equipment_effects_flow_into_stats():
    engine = _engine()
    armor = Armor(
        form_id=0xAA,
        editor_id="ArmorAA",
        name="Strength Armor",
        value=20,
        health=100,
        weight=15.0,
        damage_threshold=6.0,
        equipment_slot=5,
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
    weapon = Weapon(
        form_id=0xBB,
        editor_id="WeaponBB",
        name="Service Rifle",
        value=35,
        health=120,
        weight=8.0,
        damage=18,
        clip_size=24,
        crit_damage=10,
        crit_multiplier=1.0,
        equipment_slot=5,
        enchantment_form_id=None,
        is_playable=True,
    )
    engine.set_equipment(5, 0xAA)

    ui = BuildUiModel(engine, armors={0xAA: armor}, weapons={0xBB: weapon})
    catalog = ui.gear_catalog()
    assert [c.name for c in catalog] == ["Strength Armor", "Service Rifle"]
    assert len(ui.gear_catalog("rifle")) == 1
    assert catalog[0].conditional_effects == 0
    assert catalog[0].excluded_conditional_effects == 0

    snap = ui.level_snapshot(1)
    assert snap.stats.effective_special[AV.STRENGTH] == 9


def test_diagnostics_reports_raw_condition_block_for_selected_perk():
    perk = _perk(0x3333, min_level=2)
    perk.raw_conditions = [
        RawCondition(function=449, operator="==", value=1.0, param1=0x1234, param2=0),
    ]
    graph = DependencyGraph.build([perk], raw_condition_policy="strict")
    engine = BuildEngine(GameSettings.defaults(), graph)
    engine.set_special({
        AV.STRENGTH: 7,
        AV.PERCEPTION: 7,
        AV.ENDURANCE: 6,
        AV.CHARISMA: 6,
        AV.INTELLIGENCE: 5,
        AV.AGILITY: 5,
        AV.LUCK: 4,
    })
    engine.set_sex(0)
    engine.set_tagged_skills({AV.GUNS, AV.LOCKPICK, AV.SPEECH})
    engine.set_target_level(2)
    # Force selection to simulate persisted/legacy invalid state.
    engine._state.level_plans[2].perk = 0x3333

    ui = BuildUiModel(engine)
    diagnostics = ui.diagnostics()
    assert any(d.code == "perk_raw_conditions_blocked" for d in diagnostics)


def test_diagnostics_reports_equipment_conditional_effect_exclusions():
    engine = _engine()
    armor = Armor(
        form_id=0xAA,
        editor_id="ArmorAA",
        name="Conditional Armor",
        value=20,
        health=100,
        weight=15.0,
        damage_threshold=6.0,
        equipment_slot=5,
        enchantment_form_id=None,
        is_playable=True,
        conditional_effects_excluded=2,
    )
    engine.set_equipment(5, 0xAA)
    ui = BuildUiModel(engine, armors={0xAA: armor}, weapons={})
    diagnostics = ui.diagnostics()
    assert any(d.code == "equipment_conditional_effects_excluded" for d in diagnostics)

    catalog = ui.gear_catalog("conditional")
    assert len(catalog) == 1
    assert catalog[0].excluded_conditional_effects == 2
