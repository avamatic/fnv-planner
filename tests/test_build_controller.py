from pathlib import Path

from fnv_planner.engine.build_engine import BuildEngine
from fnv_planner.engine.ui_model import BuildUiModel
from fnv_planner.graph.dependency_graph import DependencyGraph
from fnv_planner.models.constants import ActorValue
from fnv_planner.models.game_settings import GameSettings
from fnv_planner.models.perk import Perk
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


def test_apply_real_build_perk_preset_by_name(tmp_path):
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
    preset = tmp_path / "real_build_perks.txt"
    preset.write_text("Educated\n")
    c.real_build_perk_preset_path = preset

    ok, message = c.apply_real_build_perk_preset()
    assert ok is True
    assert message is not None
    assert c.selected_perk_ids() == {perk.form_id}


def test_apply_real_build_perk_preset_missing_file():
    c = _controller({})
    c.real_build_perk_preset_path = Path("config/does_not_exist_real_build_perks.txt")

    ok, message = c.apply_real_build_perk_preset()
    assert ok is False
    assert message is not None
    assert "not found" in message.lower()


def test_implant_points_by_level_reports_creation_implant_allocation():
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
    assert c.implant_points_by_level() == {2: {int(AV.PERCEPTION): 1}}
