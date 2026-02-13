from fnv_planner.engine.build_engine import BuildEngine
from fnv_planner.graph.dependency_graph import DependencyGraph
from fnv_planner.models.constants import SKILL_GOVERNING_ATTRIBUTE, ActorValue
from fnv_planner.models.game_settings import GameSettings
from fnv_planner.models.perk import Perk, PerkEntryPointEffect, SkillRequirement
from fnv_planner.optimizer.planner import plan_build
from fnv_planner.optimizer.specs import GoalSpec, RequirementSpec, StartingConditions


AV = ActorValue


def _perk(
    *,
    form_id: int,
    name: str,
    editor_id: str | None = None,
    description: str = "",
    min_level: int = 2,
    ranks: int = 1,
    is_playable: bool = True,
    is_hidden: bool = False,
    is_trait: bool = False,
    skill_requirements: list[SkillRequirement] | None = None,
    entry_point_effects: list[PerkEntryPointEffect] | None = None,
) -> Perk:
    return Perk(
        form_id=form_id,
        editor_id=editor_id or name.replace(" ", ""),
        name=name,
        description=description,
        is_trait=is_trait,
        min_level=min_level,
        ranks=ranks,
        is_playable=is_playable,
        is_hidden=is_hidden,
        skill_requirements=skill_requirements or [],
        entry_point_effects=entry_point_effects or [],
    )


def _engine(perks: list[Perk]) -> BuildEngine:
    return BuildEngine(GameSettings.defaults(), DependencyGraph.build(perks))


def _balanced_special() -> dict[int, int]:
    return {
        int(AV.STRENGTH): 7,
        int(AV.PERCEPTION): 7,
        int(AV.ENDURANCE): 6,
        int(AV.CHARISMA): 6,
        int(AV.INTELLIGENCE): 5,
        int(AV.AGILITY): 5,
        int(AV.LUCK): 4,
    }


def _starting(target_level: int) -> StartingConditions:
    return StartingConditions(
        sex=0,
        special=_balanced_special(),
        tagged_skills={int(AV.GUNS), int(AV.LOCKPICK), int(AV.SPEECH)},
        target_level=target_level,
    )


def test_plan_build_selects_required_perk_when_feasible():
    perk = _perk(
        form_id=0x1000,
        name="Guns Gate",
        min_level=2,
        skill_requirements=[
            SkillRequirement(
                actor_value=int(AV.GUNS),
                name="Guns",
                operator=">=",
                value=30,
            )
        ],
    )
    engine = _engine([perk])
    result = plan_build(
        engine,
        GoalSpec(required_perks=[perk.form_id], target_level=2),
        starting=_starting(target_level=2),
        perks_by_id={perk.form_id: perk},
    )

    assert result.success is True
    assert result.missing_required_perks == []
    assert result.selected_required_perks == [perk.form_id]
    assert result.state.level_plans[2].perk == perk.form_id


def test_plan_build_reports_missing_required_perk_when_infeasible():
    perk = _perk(
        form_id=0x2000,
        name="Impossible Guns Gate",
        min_level=2,
        skill_requirements=[
            SkillRequirement(
                actor_value=int(AV.GUNS),
                name="Guns",
                operator=">=",
                value=100,
            )
        ],
    )
    engine = _engine([perk])
    result = plan_build(
        engine,
        GoalSpec(required_perks=[perk.form_id], target_level=2),
        starting=_starting(target_level=2),
        perks_by_id={perk.form_id: perk},
    )

    assert result.success is False
    assert result.selected_required_perks == []
    assert result.missing_required_perks == [perk.form_id]
    assert any("Could not schedule required perk" in msg for msg in result.messages)


def test_plan_build_resets_stale_progression_before_solving():
    perk = _perk(form_id=0x3000, name="Reusable Requirement", min_level=2)
    engine = _engine([perk])

    # Seed creation + a stale previous plan where the perk is already selected.
    start = _starting(target_level=2)
    engine.set_sex(start.sex or 0)
    engine.set_special(start.special or {})
    engine.set_tagged_skills(start.tagged_skills or set())
    engine.set_target_level(2)
    engine.select_perk(2, perk.form_id)

    # Planner should solve from a fresh progression state, not inherit stale picks.
    result = plan_build(
        engine,
        GoalSpec(required_perks=[perk.form_id], target_level=2),
        starting=start,
        perks_by_id={perk.form_id: perk},
    )

    assert result.success is True
    assert result.missing_required_perks == []
    assert result.state.level_plans[2].perk == perk.form_id


def test_plan_build_uses_intense_training_for_special_gate():
    intense = _perk(
        form_id=0x9001,
        name="Intense Training",
        editor_id="IntenseTraining",
        min_level=2,
        ranks=10,
        entry_point_effects=[
            PerkEntryPointEffect(
                entry_point=0,
                rank_index=0,
                priority=0,
                data_payloads=[bytes.fromhex("b238000065cdcdcd")],
            )
        ],
    )
    required = _perk(
        form_id=0x9002,
        name="Strength Gate",
        min_level=4,
        skill_requirements=[
            SkillRequirement(
                actor_value=int(AV.STRENGTH),
                name="Strength",
                operator=">=",
                value=8,
            )
        ],
    )
    engine = _engine([intense, required])
    result = plan_build(
        engine,
        GoalSpec(required_perks=[required.form_id], target_level=4),
        starting=_starting(target_level=4),
        perks_by_id={p.form_id: p for p in [intense, required]},
    )

    assert result.success is True
    assert result.missing_required_perks == []
    assert result.state.level_plans[2].perk == intense.form_id
    assert result.state.level_plans[2].special_points.get(int(AV.STRENGTH), 0) == 1
    assert result.state.level_plans[4].perk == required.form_id


def test_plan_build_uses_special_implant_for_special_gate():
    implant = _perk(
        form_id=0x9101,
        name="Perception Implant",
        description="An implant that increases your Perception by 1.",
        min_level=2,
        is_playable=False,
    )
    required = _perk(
        form_id=0x9102,
        name="Perception Gate",
        min_level=2,
        skill_requirements=[
            SkillRequirement(
                actor_value=int(AV.PERCEPTION),
                name="Perception",
                operator=">=",
                value=8,
            )
        ],
    )
    engine = _engine([implant, required])
    result = plan_build(
        engine,
        GoalSpec(required_perks=[required.form_id], target_level=2),
        starting=_starting(target_level=2),
        perks_by_id={p.form_id: p for p in [implant, required]},
    )

    assert result.success is True
    assert result.missing_required_perks == []
    assert result.state.creation_special_points.get(int(AV.PERCEPTION), 0) == 1
    assert result.state.level_plans[2].special_points.get(int(AV.PERCEPTION), 0) == 0
    assert result.state.level_plans[2].perk == required.form_id


def test_plan_build_satisfies_actor_value_requirement_by_deadline():
    engine = _engine([])
    result = plan_build(
        engine,
        GoalSpec(
            target_level=4,
            requirements=[
                RequirementSpec(
                    kind="actor_value",
                    actor_value=int(AV.SCIENCE),
                    operator=">=",
                    value=40,
                    by_level=4,
                    priority=300,
                    reason="science dialogue check",
                )
            ],
        ),
        starting=_starting(target_level=4),
        perks_by_id={},
    )

    assert result.success is True
    assert result.unmet_requirements == []


def test_plan_build_reports_unmet_actor_value_requirement():
    engine = _engine([])
    result = plan_build(
        engine,
        GoalSpec(
            target_level=2,
            requirements=[
                RequirementSpec(
                    kind="actor_value",
                    actor_value=int(AV.STRENGTH),
                    operator=">=",
                    value=9,
                    by_level=2,
                    priority=500,
                    reason="dialogue strength gate",
                )
            ],
        ),
        starting=_starting(target_level=2),
        perks_by_id={},
    )

    assert result.success is False
    assert result.unmet_requirements
    assert "dialogue strength gate" in result.unmet_requirements[0]


def test_plan_build_uses_skill_books_for_skill_actor_value_requirement():
    engine = _engine([])
    result = plan_build(
        engine,
        GoalSpec(
            target_level=2,
            requirements=[
                RequirementSpec(
                    kind="actor_value",
                    actor_value=int(AV.SCIENCE),
                    operator=">=",
                    value=28,
                    by_level=2,
                    priority=500,
                    reason="science check with books",
                )
            ],
            skill_books_by_av={int(AV.SCIENCE): 1},
        ),
        starting=_starting(target_level=2),
        perks_by_id={},
    )

    assert result.success is True
    assert result.unmet_requirements == []
    assert result.skill_books_used.get(int(AV.SCIENCE), 0) == 1


def test_plan_build_comprehension_doubles_skill_book_value():
    comprehension = _perk(
        form_id=0x9201,
        name="Book Tech",
        editor_id="BookTechPerk",
        min_level=2,
        entry_point_effects=[
            PerkEntryPointEffect(
                entry_point=2,
                rank_index=0,
                priority=0,
                data_payloads=[bytes([11, 2, 1])],
                epft=1,
                epfd=b"\x00\x00\x80\x3f",  # +1 per skill book
            )
        ],
    )
    engine = _engine([comprehension])
    result = plan_build(
        engine,
        GoalSpec(
            target_level=2,
            requirements=[
                RequirementSpec(
                    kind="perk",
                    perk_id=comprehension.form_id,
                    perk_rank=1,
                    priority=500,
                    reason="book efficiency",
                ),
                RequirementSpec(
                    kind="actor_value",
                    actor_value=int(AV.SCIENCE),
                    operator=">=",
                    value=29,
                    by_level=2,
                    priority=400,
                    reason="science check with comprehension",
                ),
            ],
            skill_books_by_av={int(AV.SCIENCE): 1},
        ),
        starting=_starting(target_level=2),
        perks_by_id={comprehension.form_id: comprehension},
    )

    assert result.success is True
    assert result.state.level_plans[2].perk == comprehension.form_id
    assert result.skill_books_used.get(int(AV.SCIENCE), 0) == 1


def test_plan_build_max_skills_raises_starting_intelligence():
    engine = _engine([])
    start = StartingConditions(
        sex=0,
        special={
            int(AV.STRENGTH): 8,
            int(AV.PERCEPTION): 8,
            int(AV.ENDURANCE): 8,
            int(AV.CHARISMA): 8,
            int(AV.INTELLIGENCE): 1,
            int(AV.AGILITY): 4,
            int(AV.LUCK): 3,
        },
        tagged_skills={int(AV.GUNS), int(AV.LOCKPICK), int(AV.SPEECH)},
        target_level=2,
    )
    result = plan_build(
        engine,
        GoalSpec(
            target_level=2,
            requirements=[RequirementSpec(kind="max_skills", priority=100, reason="max skills")],
        ),
        starting=start,
        perks_by_id={},
    )

    assert result.success in {True, False}
    assert result.state.special[int(AV.INTELLIGENCE)] == 10


def test_plan_build_max_skills_accounts_for_skilled_trait_bonus():
    skilled = _perk(
        form_id=0x5000,
        name="Skilled",
        editor_id="TraitSkilled",
        is_trait=True,
        min_level=1,
        entry_point_effects=[
            PerkEntryPointEffect(
                entry_point=1,
                rank_index=0,
                priority=0,
                data_payloads=[bytes.fromhex("ad330101")],
            )
        ],
    )
    engine = _engine([skilled])
    start = StartingConditions(
        sex=0,
        special=_balanced_special(),
        tagged_skills={int(AV.GUNS), int(AV.LOCKPICK), int(AV.SPEECH)},
        traits=[skilled.form_id],
        target_level=50,
    )

    books_budget = {int(av): 14 for av in SKILL_GOVERNING_ATTRIBUTE}

    without_trait = plan_build(
        _engine([]),
        GoalSpec(
            target_level=50,
            requirements=[RequirementSpec(kind="max_skills", priority=100, reason="max skills")],
            skill_books_by_av=books_budget,
        ),
        starting=StartingConditions(
            sex=0,
            special=_balanced_special(),
            tagged_skills={int(AV.GUNS), int(AV.LOCKPICK), int(AV.SPEECH)},
            target_level=50,
        ),
        perks_by_id={},
    )
    with_trait = plan_build(
        engine,
        GoalSpec(
            target_level=50,
            requirements=[RequirementSpec(kind="max_skills", priority=100, reason="max skills")],
            skill_books_by_av=books_budget,
        ),
        starting=start,
        perks_by_id={skilled.form_id: skilled},
        linked_spell_names_by_form={0x010133AD: "Skilled Bonus (+5 to skills)"},
    )

    assert without_trait.success is False
    assert with_trait.success is False
    without_unmet = " | ".join(without_trait.unmet_requirements)
    with_unmet = " | ".join(with_trait.unmet_requirements)
    assert without_unmet != with_unmet
    assert "32:81" in without_unmet
    assert "32:81" not in with_unmet


def test_plan_build_can_satisfy_experience_multiplier_requirement():
    learner = _perk(
        form_id=0x9301,
        name="Quick Study",
        editor_id="QuickStudy",
        min_level=2,
        entry_point_effects=[
            PerkEntryPointEffect(
                entry_point=2,
                rank_index=0,
                priority=0,
                data_payloads=[bytes([9, 3, 1])],
                epft=1,
                epfd=b"\xcd\xcc\x8c\x3f",  # 1.1x XP
            )
        ],
    )
    engine = _engine([learner])
    result = plan_build(
        engine,
        GoalSpec(
            target_level=2,
            requirements=[
                RequirementSpec(
                    kind="experience_multiplier",
                    operator=">=",
                    value_float=110.0,
                    priority=400,
                    reason="xp route",
                )
            ],
            maximize_skills=False,
        ),
        starting=_starting(target_level=2),
        perks_by_id={learner.form_id: learner},
    )

    assert result.success is True
    assert result.state.level_plans[2].perk == learner.form_id


def test_plan_build_can_satisfy_damage_multiplier_requirement():
    bruiser = _perk(
        form_id=0x9302,
        name="Bruiser Doctrine",
        editor_id="BruiserDoctrine",
        min_level=2,
        entry_point_effects=[
            PerkEntryPointEffect(
                entry_point=2,
                rank_index=0,
                priority=0,
                data_payloads=[bytes([0, 3, 3])],
                epft=1,
                epfd=b"\x9a\x99\x99\x3f",  # 1.2x damage
            )
        ],
    )
    engine = _engine([bruiser])
    result = plan_build(
        engine,
        GoalSpec(
            target_level=2,
            requirements=[
                RequirementSpec(
                    kind="damage_multiplier",
                    operator=">=",
                    value_float=120.0,
                    priority=350,
                    reason="damage check",
                )
            ],
            maximize_skills=False,
        ),
        starting=_starting(target_level=2),
        perks_by_id={bruiser.form_id: bruiser},
    )

    assert result.success is True
    assert result.state.level_plans[2].perk == bruiser.form_id


def test_plan_build_can_satisfy_crit_chance_bonus_requirement():
    finesse_like = _perk(
        form_id=0x9303,
        name="Precision",
        editor_id="PrecisionPerk",
        min_level=2,
        entry_point_effects=[
            PerkEntryPointEffect(
                entry_point=1,
                rank_index=0,
                priority=0,
                data_payloads=[bytes.fromhex("c04e0900")],  # linked-form spell
            )
        ],
    )
    engine = _engine([finesse_like])
    result = plan_build(
        engine,
        GoalSpec(
            target_level=2,
            requirements=[
                RequirementSpec(
                    kind="crit_chance_bonus",
                    operator=">=",
                    value_float=5.0,
                    priority=360,
                    reason="crit check",
                )
            ],
            maximize_skills=False,
        ),
        starting=_starting(target_level=2),
        perks_by_id={finesse_like.form_id: finesse_like},
        linked_spell_stat_bonuses_by_form={0x00094EC0: {14: 5.0}},
    )

    assert result.success is True
    assert result.state.level_plans[2].perk == finesse_like.form_id


def test_max_skills_does_not_pick_book_perk_when_books_have_no_utility():
    # Trait overcaps all skills so max-skills has no remaining deficits.
    overcap_trait = _perk(
        form_id=0x9401,
        name="Overcap",
        editor_id="TraitOvercap",
        is_trait=True,
        min_level=1,
        description="+100 to all skills.",
    )
    comprehension_like = _perk(
        form_id=0x9402,
        name="Book Tech",
        editor_id="BookTechPerk",
        min_level=2,
        entry_point_effects=[
            PerkEntryPointEffect(
                entry_point=2,
                rank_index=0,
                priority=0,
                data_payloads=[bytes([11, 2, 1])],
                epft=1,
                epfd=b"\x00\x00\x80\x3f",
            )
        ],
    )
    engine = _engine([overcap_trait, comprehension_like])
    start = StartingConditions(
        sex=0,
        special=_balanced_special(),
        tagged_skills={int(AV.GUNS), int(AV.LOCKPICK), int(AV.SPEECH)},
        traits=[overcap_trait.form_id],
        target_level=2,
    )
    result = plan_build(
        engine,
        GoalSpec(
            target_level=2,
            requirements=[RequirementSpec(kind="max_skills", priority=100, reason="max skills")],
            skill_books_by_av={int(av): 99 for av in SKILL_GOVERNING_ATTRIBUTE},
        ),
        starting=start,
        perks_by_id={overcap_trait.form_id: overcap_trait, comprehension_like.form_id: comprehension_like},
    )

    assert result.success is True
    assert result.state.level_plans[2].perk is None


def test_max_skills_trait_autopick_avoids_mixed_positive_negative_skill_trait():
    skilled = _perk(
        form_id=0x9501,
        name="Skilled",
        editor_id="TraitSkilled",
        is_trait=True,
        min_level=1,
        entry_point_effects=[
            PerkEntryPointEffect(
                entry_point=1,
                rank_index=0,
                priority=0,
                data_payloads=[bytes.fromhex("ad330101")],
            )
        ],
    )
    good_natured = _perk(
        form_id=0x9502,
        name="Good Natured",
        editor_id="TraitGoodNatured",
        is_trait=True,
        min_level=1,
        entry_point_effects=[
            PerkEntryPointEffect(
                entry_point=1,
                rank_index=0,
                priority=0,
                data_payloads=[bytes.fromhex("ae330101")],
            )
        ],
    )
    perks = {skilled.form_id: skilled, good_natured.form_id: good_natured}
    engine = _engine([skilled, good_natured])
    result = plan_build(
        engine,
        GoalSpec(
            target_level=50,
            requirements=[RequirementSpec(kind="max_skills", priority=100, reason="max skills")],
            skill_books_by_av={int(av): 12 for av in SKILL_GOVERNING_ATTRIBUTE},
        ),
        starting=_starting(target_level=50),
        perks_by_id=perks,
        linked_spell_names_by_form={
            0x010133AD: "Skilled Bonus (+5 to skills)",
            0x010133AE: "Good Natured (+5 to non-combat skills, -5 to combat skills)",
        },
        linked_spell_stat_bonuses_by_form={
            0x010133AD: {int(av): 5.0 for av in SKILL_GOVERNING_ATTRIBUTE},
            0x010133AE: {
                int(AV.BARTER): 5.0,
                int(AV.MEDICINE): 5.0,
                int(AV.REPAIR): 5.0,
                int(AV.SCIENCE): 5.0,
                int(AV.SPEECH): 5.0,
                int(AV.ENERGY_WEAPONS): -5.0,
                int(AV.EXPLOSIVES): -5.0,
                int(AV.GUNS): -5.0,
                int(AV.MELEE_WEAPONS): -5.0,
                int(AV.UNARMED): -5.0,
            },
        },
    )

    assert skilled.form_id in result.state.traits
    assert good_natured.form_id not in result.state.traits
