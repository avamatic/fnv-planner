from fnv_planner.engine.build_engine import BuildEngine
from fnv_planner.engine.ui_model import BuildUiModel
from fnv_planner.graph.dependency_graph import DependencyGraph
from fnv_planner.models.constants import ActorValue
from fnv_planner.models.game_settings import GameSettings
from fnv_planner.models.perk import Perk
from fnv_planner.ui.controllers.progression_controller import ProgressionController
from fnv_planner.ui.state import UiState


AV = ActorValue


def _perk(form_id: int, min_level: int = 1) -> Perk:
    return Perk(
        form_id=form_id,
        editor_id=f"P{form_id:x}",
        name=f"Perk {form_id:x}",
        description="",
        is_trait=False,
        min_level=min_level,
        ranks=1,
        is_playable=True,
        is_hidden=False,
    )


def _engine() -> BuildEngine:
    graph = DependencyGraph.build([_perk(0x1000, min_level=2)])
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
    engine.allocate_skill_points(2, {AV.SCIENCE: 1})
    return engine


def test_progression_controller_applies_book_points_to_effective_skills():
    engine = _engine()
    ui = BuildUiModel(engine)
    controller = ProgressionController(
        engine=engine,
        ui_model=ui,
        perks={},
        state=UiState(),
    )
    controller.set_skill_book_usage(
        needed=1,
        available=1,
        rows=[("Science", 1, 1)],
        by_level={2: {int(AV.SCIENCE): 1}},
        points_by_level={2: {int(AV.SCIENCE): 2}},
    )

    base_l1 = ui.level_snapshot(1).stats.skills
    base_l2 = ui.level_snapshot(2).stats.skills

    effective_l1 = controller.effective_skills_for_level(1, base_l1)
    effective_l2 = controller.effective_skills_for_level(2, base_l2)

    assert effective_l1[int(AV.SCIENCE)] == base_l1[int(AV.SCIENCE)]
    assert effective_l2[int(AV.SCIENCE)] == base_l2[int(AV.SCIENCE)] + 2


def test_progression_controller_renders_between_level_book_step_label():
    engine = _engine()
    controller = ProgressionController(
        engine=engine,
        ui_model=BuildUiModel(engine),
        perks={},
        state=UiState(),
    )
    controller.set_skill_book_usage(
        needed=1,
        available=1,
        rows=[("Science", 1, 1)],
        by_level={2: {int(AV.SCIENCE): 1}},
        points_by_level={2: {int(AV.SCIENCE): 2}},
    )

    label = controller.skill_books_between_levels_label(1, 2)
    assert label is not None
    assert "Between L1 and L2" in label
    assert "Science +1 book(s) (+2 skill)" in label


def test_progression_controller_renders_between_level_implant_step_label():
    engine = _engine()
    controller = ProgressionController(
        engine=engine,
        ui_model=BuildUiModel(engine),
        perks={},
        state=UiState(),
    )
    controller.set_implant_usage_by_level({2: {int(AV.PERCEPTION): 1}})

    label = controller.implants_between_levels_label(1, 2)
    assert label is not None
    assert "Between L1 and L2" in label
    assert "Perception +1 implant point(s)" in label


def test_progression_controller_renders_between_level_zero_cost_perk_label():
    engine = _engine()
    controller = ProgressionController(
        engine=engine,
        ui_model=BuildUiModel(engine),
        perks={},
        state=UiState(),
    )
    controller.set_zero_cost_perks_by_level({2: ["Challenge Reward [challenge]"]})

    label = controller.zero_cost_perks_between_levels_label(1, 2)
    assert label is not None
    assert "Between L1 and L2" in label
    assert "Challenge Reward [challenge]" in label
