from fnv_planner.engine.build_engine import BuildEngine
from fnv_planner.engine.ui_model import BuildUiModel
from fnv_planner.graph.dependency_graph import DependencyGraph
from fnv_planner.models.constants import ActorValue
from fnv_planner.models.game_settings import GameSettings
from fnv_planner.ui.controllers.build_controller import BuildController
from fnv_planner.ui.state import UiState


AV = ActorValue


def _controller(skill_books_by_av: dict[int, int]) -> BuildController:
    engine = BuildEngine(GameSettings.defaults(), DependencyGraph.build([]))
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
        perks={},
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
