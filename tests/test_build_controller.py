from fnv_planner.engine.build_engine import BuildEngine
from fnv_planner.engine.ui_model import BuildUiModel
from fnv_planner.graph.dependency_graph import DependencyGraph
from fnv_planner.models.constants import ActorValue
from fnv_planner.models.game_settings import GameSettings
from fnv_planner.models.perk import Perk
from fnv_planner.optimizer.planner import PlanResult
from fnv_planner.ui.controllers.build_controller import BuildController
from fnv_planner.ui.state import UiState


AV = ActorValue


def _controller(
    skill_books_by_av: dict[int, int],
    *,
    perks: dict[int, Perk] | None = None,
) -> BuildController:
    perk_rows = list((perks or {}).values())
    engine = BuildEngine(GameSettings.defaults(), DependencyGraph.build(perk_rows))
    engine.set_special(
        {
            AV.STRENGTH: 5,
            AV.PERCEPTION: 5,
            AV.ENDURANCE: 5,
            AV.CHARISMA: 5,
            AV.INTELLIGENCE: 5,
            AV.AGILITY: 5,
            AV.LUCK: 10,
        }
    )
    engine.set_sex(0)
    engine.set_tagged_skills({int(AV.GUNS), int(AV.LOCKPICK), int(AV.SPEECH)})
    engine.set_target_level(10)
    return BuildController(
        engine=engine,
        ui_model=BuildUiModel(engine),
        perks=perks or {},
        challenge_perk_ids=set(),
        skill_books_by_av=skill_books_by_av,
        linked_spell_names_by_form={},
        linked_spell_stat_bonuses_by_form={},
        state=UiState(),
    )


def test_max_skills_auto_selects_tagged_skills():
    c = _controller(
        {
            int(AV.SURVIVAL): 1,
            int(AV.BARTER): 2,
            int(AV.SCIENCE): 3,
            int(AV.GUNS): 99,
            int(AV.SPEECH): 99,
            int(AV.LOCKPICK): 99,
            int(AV.SNEAK): 99,
            int(AV.MEDICINE): 99,
            int(AV.MELEE_WEAPONS): 99,
            int(AV.ENERGY_WEAPONS): 99,
            int(AV.EXPLOSIVES): 99,
            int(AV.REPAIR): 99,
            int(AV.UNARMED): 99,
        }
    )
    c.add_max_skills_request()

    rows = c.selected_tagged_skills_rows()
    names = {name for name, _source in rows}
    assert names == {"Survival", "Barter", "Science"}
    assert all(source == "Auto (Max Skills)" for _name, source in rows)


def test_direct_tagged_skill_requests_override_auto_selection():
    c = _controller({})
    ok, message = c.set_tagged_skill_requests(
        {int(AV.SCIENCE), int(AV.MEDICINE), int(AV.REPAIR)}
    )
    assert ok is True
    assert message is None

    rows = c.selected_tagged_skills_rows()
    names = {name for name, _source in rows}
    assert names == {"Science", "Medicine", "Repair"}
    assert all(source == "Direct request" for _name, source in rows)


def test_tagged_skill_requests_are_limited_to_three():
    c = _controller({})
    ok, message = c.set_tagged_skill_requests(
        {int(AV.SCIENCE), int(AV.MEDICINE), int(AV.REPAIR), int(AV.SPEECH)}
    )
    assert ok is False
    assert message is not None
    assert len(c.selected_tagged_skills_rows()) == 3


def test_apply_quick_perk_preset_by_editor_id(tmp_path):
    perk = Perk(
        form_id=0x31DD8,
        editor_id="Educated",
        name="Educated",
        description="",
        is_trait=False,
        min_level=4,
        ranks=1,
        is_playable=True,
        is_hidden=False,
    )
    c = _controller({})
    c.perks = {perk.form_id: perk}
    preset = tmp_path / "quick_perks.txt"
    preset.write_text("Educated\n")
    c.quick_perk_preset_path = preset

    ok, message = c.apply_quick_perk_preset()
    assert ok is True
    assert message is not None
    assert c.selected_perk_ids() == {perk.form_id}


def test_apply_quick_perk_preset_reports_unresolved_entries(tmp_path):
    perk = Perk(
        form_id=0x31DD8,
        editor_id="Educated",
        name="Educated",
        description="",
        is_trait=False,
        min_level=4,
        ranks=1,
        is_playable=True,
        is_hidden=False,
    )
    c = _controller({})
    c.perks = {perk.form_id: perk}
    preset = tmp_path / "quick_perks.txt"
    preset.write_text("Educated\nNoSuchPerk\n")
    c.quick_perk_preset_path = preset

    ok, message = c.apply_quick_perk_preset()
    assert ok is False
    assert message is not None
    assert "NoSuchPerk" in message
    assert c.selected_perk_ids() == {perk.form_id}


def test_zero_cost_perk_events_by_level_includes_challenge_and_special():
    challenge = Perk(
        form_id=0x7001,
        editor_id="PerkChallengeReward",
        name="Challenge Reward",
        description="",
        is_trait=False,
        min_level=6,
        ranks=1,
        is_playable=True,
        is_hidden=False,
    )
    special = Perk(
        form_id=0x7002,
        editor_id="SpecialPassive",
        name="Special Passive",
        description="",
        is_trait=False,
        min_level=4,
        ranks=1,
        is_playable=False,
        is_hidden=False,
    )
    normal = Perk(
        form_id=0x7003,
        editor_id="NormalPerk",
        name="Normal Perk",
        description="",
        is_trait=False,
        min_level=2,
        ranks=1,
        is_playable=True,
        is_hidden=False,
    )
    c = _controller({})
    c.perks = {p.form_id: p for p in [challenge, special, normal]}
    c.challenge_perk_ids = {challenge.form_id}
    c.set_perk_requests({challenge.form_id, special.form_id, normal.form_id})

    events = c.zero_cost_perk_events_by_level()
    assert events.get(4) == ["Special Passive [special]"]
    assert events.get(6) == ["Challenge Reward [challenge]"]
    assert 2 not in events


def test_max_crit_request_auto_selects_crit_bonus_perk():
    crit_perk = Perk(
        form_id=0x7100,
        editor_id="PrecisionPerk",
        name="Precision",
        description="+5% chance to get a critical hit.",
        is_trait=False,
        min_level=2,
        ranks=1,
        is_playable=True,
        is_hidden=False,
    )
    filler_perk = Perk(
        form_id=0x7101,
        editor_id="GeneralistPerk",
        name="Generalist",
        description="+10 Carry Weight.",
        is_trait=False,
        min_level=2,
        ranks=1,
        is_playable=True,
        is_hidden=False,
    )
    c = _controller(
        {},
        perks={crit_perk.form_id: crit_perk, filler_perk.form_id: filler_perk},
    )
    c.add_max_crit_request()

    rows = c.selected_perks_rows()
    assert any(name == "Precision" and source == "Auto (Max Crit)" for name, _level, source in rows)


def test_anytime_desired_perks_excludes_items_scheduled_in_zero_cost_events():
    special = Perk(
        form_id=0x7010,
        editor_id="SpecialPassive",
        name="Special Passive",
        description="",
        is_trait=False,
        min_level=4,
        ranks=1,
        is_playable=False,
        is_hidden=False,
    )
    c = _controller({})
    c.perks = {special.form_id: special}
    c.set_perk_requests({special.form_id})

    assert c.zero_cost_perk_events_by_level().get(4) == ["Special Passive [special]"]
    assert c.anytime_desired_perk_labels() == []


def test_implant_points_by_level_reports_deferred_implant_allocation():
    implant = Perk(
        form_id=0x9101,
        editor_id="PerceptionImplant",
        name="Perception Implant",
        description="An implant that increases your Perception by 1.",
        is_trait=False,
        min_level=1,
        ranks=1,
        is_playable=False,
        is_hidden=False,
    )
    c = _controller({}, perks={implant.form_id: implant})
    ok, message = c.add_actor_value_request(int(AV.PERCEPTION), 8, reason="gate")
    assert ok is True
    assert message is None
    assert c.implant_points_by_level() == {c.target_level: {int(AV.PERCEPTION): 1}}


def test_set_meta_request_enabled_can_remove_and_add_max_crit():
    c = _controller({})
    c.set_meta_request_enabled("max_crit", True)
    assert any(req["kind"] == "max_crit" for req in c.priority_request_payloads())

    c.set_meta_request_enabled("max_crit", False)
    assert not any(req["kind"] == "max_crit" for req in c.priority_request_payloads())


def test_add_crit_damage_potential_request_is_reflected_in_rows():
    c = _controller({})
    ok, message = c.add_crit_damage_potential_request(40, reason="sniper goal")
    assert ok is True
    assert message is None
    rows = c.priority_request_rows()
    assert any("Crit Dmg Potential >= 40" in text for _idx, text in rows)


def test_max_crit_damage_request_auto_selects_damage_perk():
    damage_perk = Perk(
        form_id=0x7200,
        editor_id="DamagePerk",
        name="Damage Focus",
        description="10% more damage.",
        is_trait=False,
        min_level=2,
        ranks=1,
        is_playable=True,
        is_hidden=False,
    )
    filler_perk = Perk(
        form_id=0x7201,
        editor_id="FillerPerk",
        name="Filler",
        description="+5 to Barter.",
        is_trait=False,
        min_level=2,
        ranks=1,
        is_playable=True,
        is_hidden=False,
    )
    c = _controller({}, perks={damage_perk.form_id: damage_perk, filler_perk.form_id: filler_perk})
    c.add_max_crit_damage_request()
    rows = c.selected_perks_rows()
    assert any(name == "Damage Focus" and source == "Auto (Max Crit Dmg)" for name, _lv, source in rows)


def test_perk_request_statuses_primary_vs_secondary(monkeypatch):
    green = Perk(
        form_id=0x7300,
        editor_id="AlwaysGood",
        name="Always Good",
        description="",
        is_trait=False,
        min_level=2,
        ranks=1,
        is_playable=True,
        is_hidden=False,
    )
    yellow = Perk(
        form_id=0x7301,
        editor_id="SecondaryConflict",
        name="Secondary Conflict",
        description="",
        is_trait=False,
        min_level=2,
        ranks=1,
        is_playable=True,
        is_hidden=False,
    )
    red = Perk(
        form_id=0x7302,
        editor_id="PrimaryConflict",
        name="Primary Conflict",
        description="",
        is_trait=False,
        min_level=2,
        ranks=1,
        is_playable=True,
        is_hidden=False,
    )

    c = _controller({}, perks={green.form_id: green, yellow.form_id: yellow, red.form_id: red})

    def _fake_plan_build(base_engine, goal, **_kwargs):
        perk_ids = [
            int(req.perk_id)
            for req in goal.requirements
            if req.kind == "perk" and req.perk_id is not None
        ]
        if not perk_ids:
            return PlanResult(success=True, state=base_engine.state)

        perk_id = perk_ids[0]
        other_kinds = [req.kind for req in goal.requirements if req.kind != "perk"]
        has_secondary = "max_crit" in other_kinds

        if perk_id == int(red.form_id):
            return PlanResult(
                success=False,
                state=base_engine.state,
                unmet_requirements=["Sex: Female"],
            )
        if perk_id == int(yellow.form_id):
            if has_secondary:
                return PlanResult(
                    success=False,
                    state=base_engine.state,
                    unmet_requirements=["Conflicts with secondary request"],
                )
            return PlanResult(success=True, state=base_engine.state)
        return PlanResult(success=True, state=base_engine.state)

    monkeypatch.setattr("fnv_planner.ui.controllers.build_controller.plan_build", _fake_plan_build)

    ok, message = c.add_actor_value_request(int(AV.GUNS), 75, reason="primary")
    assert ok is True
    assert message is None
    c.add_max_crit_request()

    statuses = c.perk_request_statuses([green.form_id, yellow.form_id, red.form_id])

    assert statuses[int(green.form_id)]["status"] == "green"
    assert statuses[int(yellow.form_id)]["status"] == "yellow"
    assert statuses[int(red.form_id)]["status"] == "red"
