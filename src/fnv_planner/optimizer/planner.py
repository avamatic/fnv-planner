"""Deterministic goal-driven planner (first-pass feasibility solver)."""

from __future__ import annotations

import re
import struct
from dataclasses import dataclass, field

from fnv_planner.engine.build_engine import BuildEngine, BuildState
from fnv_planner.models.constants import (
    SKILL_GOVERNING_ATTRIBUTE,
    SPECIAL_INDICES,
    ActorValue,
)
from fnv_planner.models.perk import Perk
from fnv_planner.optimizer.specs import GoalSpec, RequirementSpec, StartingConditions


@dataclass(slots=True)
class PlanResult:
    """Planner output with solved state and diagnostics."""

    success: bool
    state: BuildState
    selected_required_perks: list[int] = field(default_factory=list)
    missing_required_perks: list[int] = field(default_factory=list)
    unmet_requirements: list[str] = field(default_factory=list)
    skill_books_used: dict[int, int] = field(default_factory=dict)
    skill_books_used_by_level: dict[int, dict[int, int]] = field(default_factory=dict)
    skill_book_points_by_level: dict[int, dict[int, int]] = field(default_factory=dict)
    perk_selection_reasons: dict[int, str] = field(default_factory=dict)
    messages: list[str] = field(default_factory=list)


@dataclass(slots=True)
class InferredSkillEffects:
    skill_points_per_level_bonus: int = 0
    skill_book_points_bonus: int = 0
    all_skills_bonus: int = 0
    per_skill_bonus: dict[int, int] = field(default_factory=dict)
    selectable_special_points: int = 0
    experience_multiplier_factor: float | None = None
    damage_multiplier_factor: float | None = None
    crit_chance_bonus_flat: float = 0.0

    @property
    def is_relevant(self) -> bool:
        return (
            self.skill_points_per_level_bonus > 0
            or self.skill_book_points_bonus > 0
            or self.all_skills_bonus != 0
            or bool(self.per_skill_bonus)
            or self.selectable_special_points > 0
            or self.experience_multiplier_factor is not None
            or self.damage_multiplier_factor is not None
            or self.crit_chance_bonus_flat > 0
        )


def plan_build(
    base_engine: BuildEngine,
    goal: GoalSpec,
    *,
    starting: StartingConditions | None = None,
    perks_by_id: dict[int, Perk] | None = None,
    linked_spell_names_by_form: dict[int, str] | None = None,
    linked_spell_stat_bonuses_by_form: dict[int, dict[int, float]] | None = None,
) -> PlanResult:
    """Create a level-by-level plan to satisfy required goals."""
    engine = base_engine.copy()
    engine.reset_progression()
    messages: list[str] = []
    selected_required: list[int] = []
    perks_by_id = perks_by_id or {}
    inferred_effects_by_id = {
        int(perk_id): _infer_perk_skill_effects(
            perk,
            linked_spell_names_by_form=linked_spell_names_by_form,
            linked_spell_stat_bonuses_by_form=linked_spell_stat_bonuses_by_form,
        )
        for perk_id, perk in perks_by_id.items()
    }

    try:
        _apply_starting_conditions(engine, goal=goal, starting=starting)
    except ValueError as exc:
        return PlanResult(
            success=False,
            state=engine.state,
            missing_required_perks=list(goal.required_perks),
            messages=[f"Invalid starting conditions: {exc}"],
        )

    target = engine.state.target_level
    requirements = _normalized_requirements(goal)
    skill_books_by_av = {
        int(av): max(0, int(count))
        for av, count in (goal.skill_books_by_av or {}).items()
    }
    _auto_select_traits_for_goals(
        engine,
        requirements=requirements,
        perks_by_id=perks_by_id,
        inferred_effects_by_id=inferred_effects_by_id,
        skill_books_by_av=skill_books_by_av,
        target_level=target,
    )
    _optimize_starting_special_for_max_skills(
        engine,
        requirements=requirements,
        perks_by_id=perks_by_id,
    )
    perk_priority: dict[int, int] = {}
    for req in requirements:
        if req.kind == "perk" and req.perk_id is not None:
            perk_priority[req.perk_id] = max(perk_priority.get(req.perk_id, 0), int(req.priority))

    pending_required = [pid for pid in goal.required_perks]
    for req in requirements:
        if req.kind == "perk" and req.perk_id is not None and req.perk_id not in pending_required:
            pending_required.append(req.perk_id)

    used_implant_ids: set[int] = set()
    perk_selection_reasons: dict[int, str] = {}

    _allocate_implant_special_points(
        engine,
        level=1,
        pending_required=pending_required,
        requirements=requirements,
        perks_by_id=perks_by_id,
        used_implant_ids=used_implant_ids,
        pre_level_two=True,
    )

    for level in range(2, target + 1):
        _allocate_implant_special_points(
            engine,
            level=level,
            pending_required=pending_required,
            requirements=requirements,
            perks_by_id=perks_by_id,
            used_implant_ids=used_implant_ids,
            pre_level_two=False,
        )
        _allocate_level_skills(
            engine,
            level=level,
            pending_required=pending_required,
            requirements=requirements,
            perks_by_id=perks_by_id,
            maximize_skills=goal.maximize_skills,
            target_level=target,
            skill_books_by_av=skill_books_by_av,
            inferred_effects_by_id=inferred_effects_by_id,
        )

        if not engine.is_perk_level(level):
            continue

        available = set(engine.available_perks_at(level))
        picked = None
        for perk_id in _ordered_pending_perks(pending_required, perk_priority, perks_by_id):
            if perk_id in available:
                engine.select_perk(level, perk_id)
                pending_required.remove(perk_id)
                selected_required.append(perk_id)
                perk_selection_reasons[level] = "Required perk request."
                picked = perk_id
                break

        if picked is None and (pending_required or _has_effect_driven_requirements(requirements)):
            support = _choose_requirement_support_perk(
                engine,
                level=level,
                target_level=target,
                available=available,
                pending_required=pending_required,
                requirements=requirements,
                perks_by_id=perks_by_id,
                inferred_effects_by_id=inferred_effects_by_id,
            )
            if support is not None:
                perk_id, special_target, reason = support
                engine.select_perk(level, perk_id)
                if special_target is not None:
                    current = int(engine.stats_at(level).effective_special.get(special_target, 0))
                    if current < 10:
                        engine.allocate_special_points(level, {special_target: 1})
                        reason = f"{reason} Applied +1 SPECIAL."
                perk_selection_reasons[level] = reason
                picked = perk_id

        if picked is None and _has_max_skills_requirement(requirements):
            best = _choose_best_max_skills_perk(
                engine,
                level=level,
                target_level=target,
                available=available,
                pending_required=pending_required,
                requirements=requirements,
                perks_by_id=perks_by_id,
                inferred_effects_by_id=inferred_effects_by_id,
                skill_books_by_av=skill_books_by_av,
            )
            if best is not None:
                perk_id, special_target, reason = best
                engine.select_perk(level, perk_id)
                if special_target is not None:
                    current = int(engine.stats_at(level).effective_special.get(special_target, 0))
                    if current < 10:
                        engine.allocate_special_points(level, {special_target: 1})
                        reason = f"{reason} Applied +1 SPECIAL."
                perk_selection_reasons[level] = reason
                picked = perk_id

        if picked is None and goal.fill_perk_slots and available:
            fallback = min(available)
            engine.select_perk(level, fallback)
            perk_selection_reasons[level] = "Auto-filled open perk slot."

    if pending_required:
        for perk_id in pending_required:
            messages.append(f"Could not schedule required perk {perk_id:#x} by L{target}")

    if requirements and all(req.kind == "max_skills" for req in requirements):
        _rebalance_max_skills_with_book_constraints(
            engine,
            target_level=target,
            skill_books_by_av=skill_books_by_av,
            inferred_effects_by_id=inferred_effects_by_id,
        )

    unmet_requirements = _evaluate_unmet_requirements(
        engine,
        requirements=requirements,
        target_level=target,
        skill_books_by_av=skill_books_by_av,
        inferred_effects_by_id=inferred_effects_by_id,
    )
    if unmet_requirements:
        messages.extend(unmet_requirements)

    errors = engine.validate()
    if errors:
        messages.extend(f"L{err.level} [{err.category}] {err.message}" for err in errors)

    skill_books_used_by_level, skill_book_points_by_level = _estimate_skill_books_usage_timeline(
        engine,
        requirements=requirements,
        target_level=target,
        skill_books_by_av=skill_books_by_av,
        inferred_effects_by_id=inferred_effects_by_id,
    )
    return PlanResult(
        success=(not pending_required and not unmet_requirements and not errors),
        state=engine.state,
        selected_required_perks=selected_required,
        missing_required_perks=pending_required,
        unmet_requirements=unmet_requirements,
        skill_books_used=_aggregate_skill_books_used_by_av(skill_books_used_by_level),
        skill_books_used_by_level=skill_books_used_by_level,
        skill_book_points_by_level=skill_book_points_by_level,
        perk_selection_reasons=perk_selection_reasons,
        messages=messages,
    )


def _apply_starting_conditions(
    engine: BuildEngine,
    *,
    goal: GoalSpec,
    starting: StartingConditions | None,
) -> None:
    start = starting or StartingConditions()

    if start.name is not None:
        engine.set_name(start.name)
    if start.sex is not None:
        engine.set_sex(start.sex)
    if start.special is not None:
        engine.set_special(start.special)
    if start.tagged_skills is not None:
        engine.set_tagged_skills(set(start.tagged_skills))
    if start.traits is not None:
        engine.set_traits(list(start.traits))
    if start.equipment is not None:
        engine.set_equipment_bulk(dict(start.equipment))

    desired_target = goal.target_level
    if desired_target is None:
        desired_target = start.target_level
    if desired_target is None:
        desired_target = engine.max_level
    engine.set_target_level(desired_target)


def _auto_select_traits_for_goals(
    engine: BuildEngine,
    *,
    requirements: list[RequirementSpec],
    perks_by_id: dict[int, Perk],
    inferred_effects_by_id: dict[int, InferredSkillEffects],
    skill_books_by_av: dict[int, int],
    target_level: int,
) -> None:
    current_traits = [int(t) for t in engine.state.traits]
    if len(current_traits) >= engine.max_traits:
        return

    candidates: list[tuple[float, int]] = []
    for perk in perks_by_id.values():
        if not perk.is_trait:
            continue
        if int(perk.form_id) in current_traits:
            continue
        effects = inferred_effects_by_id.get(int(perk.form_id))
        if effects is None:
            continue
        score = _score_trait_for_goals(
            effects=effects,
            requirements=requirements,
            skill_books_by_av=skill_books_by_av,
            target_level=target_level,
        )
        if score <= 0:
            continue
        candidates.append((score, int(perk.form_id)))

    if not candidates:
        return
    candidates.sort(key=lambda x: (-x[0], x[1]))
    traits = list(current_traits)
    for _score, trait_id in candidates:
        if len(traits) >= engine.max_traits:
            break
        trial = traits + [int(trait_id)]
        try:
            engine.set_traits(trial)
        except ValueError:
            continue
        traits = trial


def _score_trait_for_goals(
    *,
    effects: InferredSkillEffects,
    requirements: list[RequirementSpec],
    skill_books_by_av: dict[int, int],
    target_level: int,
) -> float:
    score = 0.0
    if _has_max_skills_requirement(requirements):
        score += float(effects.all_skills_bonus * len(SKILL_GOVERNING_ATTRIBUTE))
        # Keep signed value so mixed traits (e.g. +5 some / -5 others) are not overvalued.
        score += float(sum(int(v) for v in effects.per_skill_bonus.values()))
        score += float(effects.skill_points_per_level_bonus * max(0, target_level - 1))
        score += float(effects.skill_book_points_bonus * sum(skill_books_by_av.values()))

    if any(r.kind == "experience_multiplier" for r in requirements) and effects.experience_multiplier_factor:
        score += max(0.0, (effects.experience_multiplier_factor - 1.0) * 100.0)
    if any(r.kind == "damage_multiplier" for r in requirements) and effects.damage_multiplier_factor:
        score += max(0.0, (effects.damage_multiplier_factor - 1.0) * 100.0)
    if any(r.kind == "crit_chance_bonus" for r in requirements):
        score += max(0.0, float(effects.crit_chance_bonus_flat))
    return score


def _normalized_requirements(goal: GoalSpec) -> list[RequirementSpec]:
    reqs = list(goal.requirements)
    for perk_id in goal.required_perks:
        reqs.append(
            RequirementSpec(
                kind="perk",
                perk_id=perk_id,
                perk_rank=1,
                priority=1000,
                reason=f"required perk {perk_id:#x}",
            )
        )
    reqs.sort(key=lambda r: (-int(r.priority), (r.by_level if r.by_level is not None else 10_000), r.reason))
    return reqs


def _optimize_starting_special_for_max_skills(
    engine: BuildEngine,
    *,
    requirements: list[RequirementSpec],
    perks_by_id: dict[int, Perk],
) -> None:
    """When max-skills is requested, bias creation SPECIAL to higher INT first.

    Keeps SPECIAL minima needed by explicit SPECIAL requirements and required
    perk SPECIAL thresholds, then spends remaining creation budget into INT.
    """
    if not _has_max_skills_requirement(requirements):
        return
    current = dict(engine.state.special)
    if set(current.keys()) != SPECIAL_INDICES:
        return

    minima = {int(av): engine.special_min for av in SPECIAL_INDICES}

    for req in requirements:
        if req.kind == "actor_value" and req.actor_value is not None and req.value is not None:
            av = int(req.actor_value)
            if av not in SPECIAL_INDICES:
                continue
            threshold = _threshold(req.operator, int(req.value))
            if threshold is None:
                continue
            minima[av] = max(minima[av], min(engine.special_max, threshold))
            continue

        if req.kind == "perk" and req.perk_id is not None:
            perk = perks_by_id.get(int(req.perk_id))
            if perk is None:
                continue
            for preq in perk.skill_requirements:
                av = int(preq.actor_value)
                if av not in SPECIAL_INDICES:
                    continue
                threshold = _threshold(preq.operator, int(preq.value))
                if threshold is None:
                    continue
                minima[av] = max(minima[av], min(engine.special_max, threshold))

    used = sum(minima.values())
    if used > engine.special_budget:
        return

    target = dict(minima)
    remaining = engine.special_budget - used

    # Max-skills policy: raise INT first whenever feasible.
    int_av = int(ActorValue.INTELLIGENCE)
    if remaining > 0 and target[int_av] < engine.special_max:
        add = min(engine.special_max - target[int_av], remaining)
        target[int_av] += add
        remaining -= add

    # Keep existing non-INT preferences where budget allows.
    for av in sorted(SPECIAL_INDICES):
        if av == int_av or remaining <= 0:
            continue
        preferred = min(engine.special_max, int(current.get(av, target[av])))
        if preferred <= target[av]:
            continue
        add = min(preferred - target[av], remaining)
        target[av] += add
        remaining -= add

    # Spend the rest deterministically.
    fill_order = [
        int(ActorValue.ENDURANCE),
        int(ActorValue.AGILITY),
        int(ActorValue.PERCEPTION),
        int(ActorValue.LUCK),
        int(ActorValue.STRENGTH),
        int(ActorValue.CHARISMA),
        int_av,
    ]
    while remaining > 0:
        changed = False
        for av in fill_order:
            if remaining <= 0:
                break
            if target[av] >= engine.special_max:
                continue
            target[av] += 1
            remaining -= 1
            changed = True
        if not changed:
            break

    engine.set_special(target)


def _ordered_pending_perks(
    pending_required: list[int],
    perk_priority: dict[int, int],
    perks_by_id: dict[int, Perk],
) -> list[int]:
    return sorted(
        pending_required,
        key=lambda pid: (
            -int(perk_priority.get(pid, 0)),
            int(perks_by_id.get(pid).min_level) if perks_by_id.get(pid) else 10_000,
            perks_by_id.get(pid).name.lower() if perks_by_id.get(pid) else f"{pid:#x}",
        ),
    )


def _allocate_level_skills(
    engine: BuildEngine,
    *,
    level: int,
    pending_required: list[int],
    requirements: list[RequirementSpec],
    perks_by_id: dict[int, Perk],
    maximize_skills: bool,
    target_level: int,
    skill_books_by_av: dict[int, int] | None = None,
    inferred_effects_by_id: dict[int, InferredSkillEffects] | None = None,
) -> None:
    budget = engine.unspent_skill_points_at(level)
    if budget <= 0:
        return

    allocation: dict[int, int] = {}
    for _ in range(budget):
        current = engine.stats_at(level).skills
        priority = _skill_priority(
            engine,
            level=level,
            current_skills=current,
            pending_required=pending_required,
            requirements=requirements,
            perks_by_id=perks_by_id,
            maximize_skills=maximize_skills,
            target_level=target_level,
            skill_books_by_av=skill_books_by_av,
            inferred_effects_by_id=inferred_effects_by_id,
        )
        ordered = sorted(
            current.keys(),
            key=lambda av: (-priority.get(av, 0.0), current.get(av, 0), av),
        )

        placed = False
        for av in ordered:
            trial = dict(allocation)
            trial[av] = trial.get(av, 0) + 1
            try:
                engine.allocate_skill_points(level, trial)
            except ValueError:
                continue
            allocation = trial
            placed = True
            break
        if not placed:
            break

    engine.allocate_skill_points(level, allocation)


def _skill_priority(
    engine: BuildEngine,
    *,
    level: int,
    current_skills: dict[int, int],
    pending_required: list[int],
    requirements: list[RequirementSpec],
    perks_by_id: dict[int, Perk],
    maximize_skills: bool,
    target_level: int,
    skill_books_by_av: dict[int, int] | None = None,
    inferred_effects_by_id: dict[int, InferredSkillEffects] | None = None,
) -> dict[int, float]:
    score: dict[int, float] = {}
    perk_levels = [lv for lv in engine.perk_levels() if lv >= level]

    for perk_id in pending_required:
        perk = perks_by_id.get(perk_id)
        if perk is None:
            continue
        deadlines = [lv for lv in perk_levels if lv >= perk.min_level]
        if not deadlines:
            continue
        deadline = deadlines[0]
        urgency = 50.0 / (1 + max(0, deadline - level))

        for req in perk.skill_requirements:
            av = int(req.actor_value)
            if av not in current_skills:
                continue
            target = _threshold(req.operator, req.value)
            if target is None:
                continue
            deficit = max(0, target - int(current_skills.get(av, 0)))
            if deficit > 0:
                score[av] = score.get(av, 0.0) + urgency + float(deficit * 2)

    for req in requirements:
        if req.kind != "actor_value" or req.actor_value is None or req.value is None:
            if req.kind != "max_skills":
                continue
            deadline = _requirement_deadline(req, target_level)
            urgency = 40.0 / (1 + max(0, deadline - level))
            importance = max(0.2, float(req.priority) / 100.0)
            flat_bonuses = _effective_flat_skill_bonuses(
                engine,
                deadline=deadline,
                inferred_effects_by_id=inferred_effects_by_id,
            )
            for av in current_skills:
                if av not in SKILL_GOVERNING_ATTRIBUTE:
                    continue
                effective = int(current_skills.get(av, 0)) + int(flat_bonuses.get(int(av), 0))
                deficit = max(0, 100 - effective)
                if deficit <= 0:
                    continue
                score[av] = score.get(av, 0.0) + (urgency * importance) + float(deficit * 1.5)
            continue
        av = int(req.actor_value)
        if av not in current_skills:
            continue
        target = _threshold(req.operator, int(req.value))
        if target is None:
            continue
        deficit = max(0, target - int(current_skills.get(av, 0)))
        if deficit <= 0:
            continue
        deadline = _requirement_deadline(req, target_level)
        urgency = 40.0 / (1 + max(0, deadline - level))
        importance = max(0.2, float(req.priority) / 100.0)
        score[av] = score.get(av, 0.0) + (urgency * importance) + float(deficit * 2)

    if maximize_skills:
        per_book = _effective_skill_book_points(
            engine,
            deadline=target_level,
            inferred_effects_by_id=inferred_effects_by_id,
        )
        flat_bonuses = _effective_flat_skill_bonuses(
            engine,
            deadline=target_level,
            inferred_effects_by_id=inferred_effects_by_id,
        )
        books = {int(av): max(0, int(v)) for av, v in (skill_books_by_av or {}).items()}
        for av in current_skills:
            if av not in SKILL_GOVERNING_ATTRIBUTE:
                continue
            headroom = max(0, 100 - int(current_skills[av]))
            effective = int(current_skills.get(av, 0)) + int(flat_bonuses.get(int(av), 0))
            deficit = max(0, 100 - effective)
            book_cover = max(0, books.get(int(av), 0) * per_book)
            uncovered = max(0, deficit - book_cover)
            score[av] = score.get(av, 0.0) + headroom * 0.05 + float(uncovered * 3.0)

    return score


def _detect_special_implants(perks_by_id: dict[int, Perk]) -> dict[int, int]:
    out: dict[int, int] = {}
    for perk in perks_by_id.values():
        if _perk_category_guess(perk) != "special":
            continue
        target = _implant_special_target(perk)
        if target is None:
            continue
        out[perk.form_id] = target
    return out


def _perk_category_guess(perk: Perk) -> str:
    if perk.is_trait:
        return "trait"
    if perk.is_hidden:
        return "internal"
    if not perk.is_playable:
        return "special"
    return "normal"


def _implant_special_target(perk: Perk) -> int | None:
    text = f"{perk.name} {perk.editor_id} {perk.description}".lower()
    if "implant" not in text:
        return None
    if "strength" in text:
        return int(ActorValue.STRENGTH)
    if "perception" in text:
        return int(ActorValue.PERCEPTION)
    if "endurance" in text:
        return int(ActorValue.ENDURANCE)
    if "charisma" in text:
        return int(ActorValue.CHARISMA)
    if "intelligence" in text:
        return int(ActorValue.INTELLIGENCE)
    if "agility" in text:
        return int(ActorValue.AGILITY)
    if "luck" in text:
        return int(ActorValue.LUCK)
    return None


def _allocate_implant_special_points(
    engine: BuildEngine,
    *,
    level: int,
    pending_required: list[int],
    requirements: list[RequirementSpec],
    perks_by_id: dict[int, Perk],
    used_implant_ids: set[int],
    pre_level_two: bool,
) -> None:
    implant_targets = _detect_special_implants(perks_by_id)
    if not implant_targets:
        return

    due_level = 2 if pre_level_two else int(level)
    deficits = _special_deficits(
        engine,
        level=level,
        pending_required=pending_required,
        requirements=requirements,
        perks_by_id=perks_by_id,
        target_level=engine.state.target_level,
        due_by_level=due_level,
    )
    use_timing_gain = pre_level_two and _has_max_skills_requirement(requirements)
    if not deficits and not use_timing_gain:
        return

    allocation: dict[int, int] = {}
    for perk_id, target_av in implant_targets.items():
        if perk_id in used_implant_ids:
            continue
        perk = perks_by_id.get(perk_id)
        if perk is None:
            continue

        unmet_level = 2 if pre_level_two else level
        unmet = engine.unmet_requirements_for_perk(perk_id, level=unmet_level)
        if unmet:
            continue
        needed_now = float(deficits.get(target_av, 0.0)) > 0.0
        if not needed_now and use_timing_gain:
            needed_now = _pre_level_two_timing_gain(
                engine,
                target_av=int(target_av),
                target_level=int(engine.state.target_level),
            ) > 0
        if not needed_now:
            continue

        current_level = 1 if pre_level_two else level
        current = int(engine.stats_at(current_level).effective_special.get(target_av, 0))
        planned = allocation.get(target_av, 0)
        if current + planned >= 10:
            continue

        allocation[target_av] = planned + 1
        deficits[target_av] = max(0.0, float(deficits.get(target_av, 0.0)) - 1.0)
        used_implant_ids.add(perk_id)

    if not allocation:
        return

    if pre_level_two:
        current = dict(engine.state.creation_special_points)
        for av, pts in allocation.items():
            current[av] = current.get(av, 0) + pts
        engine.set_creation_special_points(current)
    else:
        engine.allocate_special_points(level, allocation)


def _pre_level_two_timing_gain(
    engine: BuildEngine,
    *,
    target_av: int,
    target_level: int,
) -> int:
    """Return skill-budget gain from applying +1 SPECIAL before level 2.

    Positive values mean front-loading this SPECIAL point improves cumulative
    earned skill points by target level compared to applying it at level 2.
    """
    current = int(engine.stats_at(1).effective_special.get(int(target_av), 0))
    if current >= 10:
        return 0

    now = engine.copy()
    create = dict(now.state.creation_special_points)
    create[int(target_av)] = create.get(int(target_av), 0) + 1
    try:
        now.set_creation_special_points(create)
    except ValueError:
        return 0

    deferred = engine.copy()
    try:
        deferred.allocate_special_points(2, {int(target_av): 1})
    except ValueError:
        return 0

    return int(now.total_skill_budget(target_level) - deferred.total_skill_budget(target_level))


def _has_available_implant_for_special_target(
    engine: BuildEngine,
    *,
    level: int,
    target_av: int,
    perks_by_id: dict[int, Perk],
) -> bool:
    """True if an unselected SPECIAL implant can provide +1 to target AV now."""
    implant_targets = _detect_special_implants(perks_by_id)
    if not implant_targets:
        return False
    selected = _selected_perk_ids_by_deadline(engine, max(1, int(level)))
    unmet_level = max(2, int(level))
    for implant_id, implant_target in implant_targets.items():
        if int(implant_target) != int(target_av):
            continue
        if int(implant_id) in selected:
            continue
        # Reuse graph requirement checks (e.g., END gating via NVSE-like conditions).
        unmet = engine.unmet_requirements_for_perk(int(implant_id), level=unmet_level)
        if unmet:
            continue
        return True
    return False


def _best_special_to_raise(
    engine: BuildEngine,
    *,
    level: int,
    pending_required: list[int],
    requirements: list[RequirementSpec],
    perks_by_id: dict[int, Perk],
    target_level: int,
) -> int | None:
    deficits = _special_deficits(
        engine,
        level=level,
        pending_required=pending_required,
        requirements=requirements,
        perks_by_id=perks_by_id,
        target_level=target_level,
    )
    if not deficits:
        return None

    for av, deficit in sorted(deficits.items(), key=lambda kv: (-kv[1], kv[0])):
        if deficit <= 0:
            continue
        if av in SPECIAL_INDICES:
            return av
    return None


def _special_deficits(
    engine: BuildEngine,
    *,
    level: int,
    pending_required: list[int],
    requirements: list[RequirementSpec],
    perks_by_id: dict[int, Perk],
    target_level: int,
    due_by_level: int | None = None,
) -> dict[int, float]:
    current = engine.stats_at(level).effective_special
    deficits: dict[int, float] = {}
    perk_levels = [lv for lv in engine.perk_levels() if lv >= max(2, level)]

    for perk_id in pending_required:
        perk = perks_by_id.get(perk_id)
        if perk is None:
            continue
        deadlines = [lv for lv in perk_levels if lv >= perk.min_level]
        if not deadlines:
            continue
        deadline = int(deadlines[0])
        if due_by_level is not None and deadline > int(due_by_level):
            continue
        urgency = float(1 + max(0, 4 - (deadline - level)))
        for req in perk.skill_requirements:
            av = int(req.actor_value)
            if av not in SPECIAL_INDICES:
                continue
            threshold = _threshold(req.operator, req.value)
            if threshold is None:
                continue
            have = int(current.get(av, 0))
            if threshold > have:
                deficits[av] = deficits.get(av, 0.0) + float((threshold - have) * urgency)

    for req in requirements:
        if req.kind != "actor_value" or req.actor_value is None or req.value is None:
            continue
        av = int(req.actor_value)
        if av not in SPECIAL_INDICES:
            continue
        threshold = _threshold(req.operator, int(req.value))
        if threshold is None:
            continue
        have = int(current.get(av, 0))
        if threshold <= have:
            continue
        deadline = _requirement_deadline(req, target_level)
        if due_by_level is not None and int(deadline) > int(due_by_level):
            continue
        urgency = float(1 + max(0, 4 - (deadline - level)))
        importance = max(0.2, float(req.priority) / 100.0)
        deficits[av] = deficits.get(av, 0.0) + float((threshold - have) * urgency * importance)

    return deficits


def _evaluate_unmet_requirements(
    engine: BuildEngine,
    *,
    requirements: list[RequirementSpec],
    target_level: int,
    skill_books_by_av: dict[int, int] | None = None,
    inferred_effects_by_id: dict[int, InferredSkillEffects] | None = None,
) -> list[str]:
    unmet: list[str] = []
    books = {
        int(av): max(0, int(count))
        for av, count in (skill_books_by_av or {}).items()
    }
    ordered_requirements = sorted(
        requirements,
        key=lambda req: (
            _requirement_deadline(req, target_level),
            -int(req.priority),
            req.reason or "",
        ),
    )
    for req in ordered_requirements:
        deadline = _requirement_deadline(req, target_level)
        reason = req.reason or "unspecified reason"
        per_book = _effective_skill_book_points(
            engine,
            deadline=deadline,
            inferred_effects_by_id=inferred_effects_by_id,
        )
        flat_bonuses = _effective_flat_skill_bonuses(
            engine,
            deadline=deadline,
            inferred_effects_by_id=inferred_effects_by_id,
        )

        if req.kind == "actor_value":
            if req.actor_value is None or req.value is None:
                unmet.append(f"Requirement invalid ({reason}): actor_value/value missing")
                continue
            stats = engine.stats_at(deadline)
            av = int(req.actor_value)
            actual_raw = (
                int(stats.effective_special.get(av, 0))
                if av in SPECIAL_INDICES
                else int(stats.skills.get(av, 0))
            )
            actual = actual_raw
            target = int(req.value)
            if av not in SPECIAL_INDICES and av in SKILL_GOVERNING_ATTRIBUTE:
                actual += int(flat_bonuses.get(av, 0))
                threshold = _threshold(req.operator, target)
                if threshold is not None and threshold > actual:
                    need_books = _books_needed(threshold - actual, per_book)
                    use = min(need_books, books.get(av, 0))
                    if use > 0:
                        books[av] = books.get(av, 0) - use
                        actual += use * per_book
            if not _compare(actual, req.operator, target):
                unmet.append(
                    f"Requirement unmet (p{req.priority}) by L{deadline}: "
                    f"AV {av} {req.operator} {target} (actual {actual_raw}) [{reason}]"
                )
            continue

        if req.kind == "perk":
            if req.perk_id is None:
                unmet.append(f"Requirement invalid ({reason}): perk_id missing")
                continue
            char = engine.materialize(deadline)
            owned = 0
            for perk_ids in char.perks.values():
                owned += perk_ids.count(int(req.perk_id))
            need_rank = max(1, int(req.perk_rank))
            if owned < need_rank:
                unmet.append(
                    f"Requirement unmet (p{req.priority}) by L{deadline}: "
                    f"perk {int(req.perk_id):#x} rank>={need_rank} (actual {owned}) [{reason}]"
                )
            continue

        if req.kind == "trait":
            if req.trait_id is None:
                unmet.append(f"Requirement invalid ({reason}): trait_id missing")
                continue
            char = engine.materialize(1)
            if int(req.trait_id) not in set(char.traits):
                unmet.append(
                    f"Requirement unmet (p{req.priority}) by L{deadline}: "
                    f"trait {int(req.trait_id):#x} not selected [{reason}]"
                )
            continue

        if req.kind == "max_skills":
            stats = engine.stats_at(deadline)
            missing: list[str] = []
            for av, val in sorted(stats.skills.items()):
                if av not in SKILL_GOVERNING_ATTRIBUTE:
                    continue
                effective = int(val) + int(flat_bonuses.get(int(av), 0))
                deficit = max(0, 100 - effective)
                if deficit <= 0:
                    continue
                use = min(_books_needed(deficit, per_book), books.get(int(av), 0))
                if use > 0:
                    books[int(av)] = books.get(int(av), 0) - use
                    deficit -= use * per_book
                if deficit > 0:
                    missing.append(f"{av}:{val}")
            if missing:
                sample = ", ".join(missing[:4])
                suffix = "" if len(missing) <= 4 else " ..."
                unmet.append(
                    f"Requirement unmet (p{req.priority}) by L{deadline}: "
                    f"max skills not reached ({sample}{suffix}) [{reason}]"
                )
            continue

        if req.kind == "experience_multiplier":
            target_pct = (
                float(req.value_float)
                if req.value_float is not None
                else float(req.value if req.value is not None else 100)
            )
            actual_pct = _effective_experience_multiplier(
                engine,
                deadline=deadline,
                inferred_effects_by_id=inferred_effects_by_id,
            ) * 100.0
            if not _compare(actual_pct, req.operator, target_pct):
                unmet.append(
                    f"Requirement unmet (p{req.priority}) by L{deadline}: "
                    f"XP {req.operator} {target_pct:g}% (actual {actual_pct:.1f}%) [{reason}]"
                )
            continue

        if req.kind == "damage_multiplier":
            target_pct = (
                float(req.value_float)
                if req.value_float is not None
                else float(req.value if req.value is not None else 100)
            )
            actual_pct = _effective_damage_multiplier(
                engine,
                deadline=deadline,
                inferred_effects_by_id=inferred_effects_by_id,
            ) * 100.0
            if not _compare(actual_pct, req.operator, target_pct):
                unmet.append(
                    f"Requirement unmet (p{req.priority}) by L{deadline}: "
                    f"Damage {req.operator} {target_pct:g}% (actual {actual_pct:.1f}%) [{reason}]"
                )
            continue

        if req.kind == "crit_chance_bonus":
            target_bonus = (
                float(req.value_float)
                if req.value_float is not None
                else float(req.value if req.value is not None else 0)
            )
            actual_bonus = _effective_crit_chance_bonus(
                engine,
                deadline=deadline,
                inferred_effects_by_id=inferred_effects_by_id,
            )
            if not _compare(actual_bonus, req.operator, target_bonus):
                unmet.append(
                    f"Requirement unmet (p{req.priority}) by L{deadline}: "
                    f"Crit bonus {req.operator} {target_bonus:g} (actual {actual_bonus:.1f}) [{reason}]"
                )
            continue

        unmet.append(f"Requirement invalid ({reason}): unknown kind '{req.kind}'")

    return unmet


def _requirement_deadline(req: RequirementSpec, target_level: int) -> int:
    if req.by_level is None:
        return target_level
    return max(1, min(int(req.by_level), target_level))


def _has_max_skills_requirement(requirements: list[RequirementSpec]) -> bool:
    return any(req.kind == "max_skills" for req in requirements)


def _has_effect_driven_requirements(requirements: list[RequirementSpec]) -> bool:
    return any(
        req.kind in {"experience_multiplier", "damage_multiplier", "crit_chance_bonus"}
        for req in requirements
    )


def _estimate_skill_books_usage_timeline(
    engine: BuildEngine,
    *,
    requirements: list[RequirementSpec],
    target_level: int,
    skill_books_by_av: dict[int, int] | None = None,
    inferred_effects_by_id: dict[int, InferredSkillEffects] | None = None,
) -> tuple[dict[int, dict[int, int]], dict[int, dict[int, int]]]:
    """Estimate skill-book usage grouped by requirement deadline level.

    Returns:
    - count timeline: level -> AV -> number of books consumed before that level-up
    - point timeline: level -> AV -> effective skill points gained from those books
    """
    books = {
        int(av): max(0, int(count))
        for av, count in (skill_books_by_av or {}).items()
    }
    used_by_level: dict[int, dict[int, int]] = {}
    points_by_level: dict[int, dict[int, int]] = {}
    ordered_requirements = sorted(
        requirements,
        key=lambda req: (
            _requirement_deadline(req, target_level),
            -int(req.priority),
            req.reason or "",
        ),
    )
    for req in ordered_requirements:
        deadline = _requirement_deadline(req, target_level)
        stats = engine.stats_at(deadline)
        per_book = _effective_skill_book_points(
            engine,
            deadline=deadline,
            inferred_effects_by_id=inferred_effects_by_id,
        )
        flat_bonuses = _effective_flat_skill_bonuses(
            engine,
            deadline=deadline,
            inferred_effects_by_id=inferred_effects_by_id,
        )

        if req.kind == "actor_value" and req.actor_value is not None and req.value is not None:
            av = int(req.actor_value)
            if av in SPECIAL_INDICES or av not in SKILL_GOVERNING_ATTRIBUTE:
                continue
            actual = int(stats.skills.get(av, 0)) + int(flat_bonuses.get(av, 0))
            threshold = _threshold(req.operator, int(req.value))
            if threshold is None or threshold <= actual:
                continue
            take = min(_books_needed(threshold - actual, per_book), books.get(av, 0))
            if take <= 0:
                continue
            used_by_level.setdefault(int(deadline), {})
            used_by_level[int(deadline)][av] = used_by_level[int(deadline)].get(av, 0) + take
            points_by_level.setdefault(int(deadline), {})
            points_by_level[int(deadline)][av] = (
                points_by_level[int(deadline)].get(av, 0) + (take * per_book)
            )
            books[av] = books.get(av, 0) - take
            continue

        if req.kind == "max_skills":
            for av, val in sorted(stats.skills.items()):
                if av not in SKILL_GOVERNING_ATTRIBUTE:
                    continue
                effective = int(val) + int(flat_bonuses.get(int(av), 0))
                deficit = max(0, 100 - effective)
                if deficit <= 0:
                    continue
                take = min(_books_needed(deficit, per_book), books.get(int(av), 0))
                if take <= 0:
                    continue
                used_by_level.setdefault(int(deadline), {})
                used_by_level[int(deadline)][int(av)] = (
                    used_by_level[int(deadline)].get(int(av), 0) + take
                )
                points_by_level.setdefault(int(deadline), {})
                points_by_level[int(deadline)][int(av)] = (
                    points_by_level[int(deadline)].get(int(av), 0) + (take * per_book)
                )
                books[int(av)] = books.get(int(av), 0) - take
    return used_by_level, points_by_level


def _aggregate_skill_books_used_by_av(
    usage_by_level: dict[int, dict[int, int]],
) -> dict[int, int]:
    used: dict[int, int] = {}
    for per_level in usage_by_level.values():
        for av, count in per_level.items():
            used[int(av)] = used.get(int(av), 0) + max(0, int(count))
    return used


def _selected_perk_ids_by_deadline(engine: BuildEngine, deadline: int) -> set[int]:
    char = engine.materialize(max(1, deadline))
    selected: set[int] = set(int(t) for t in char.traits)
    for perk_ids in char.perks.values():
        for perk_id in perk_ids:
            selected.add(int(perk_id))
    return selected


def _effective_skill_book_points(
    engine: BuildEngine,
    *,
    deadline: int,
    inferred_effects_by_id: dict[int, InferredSkillEffects] | None,
) -> int:
    base_points = max(1, int(engine.skill_book_base_points))
    if not inferred_effects_by_id:
        return base_points
    selected = _selected_perk_ids_by_deadline(engine, deadline)
    bonus = 0
    for perk_id in selected:
        effects = inferred_effects_by_id.get(int(perk_id))
        if effects is None:
            continue
        bonus += max(0, int(effects.skill_book_points_bonus))
    return max(base_points, base_points + bonus)


def _effective_flat_skill_bonuses(
    engine: BuildEngine,
    *,
    deadline: int,
    inferred_effects_by_id: dict[int, InferredSkillEffects] | None,
) -> dict[int, int]:
    out: dict[int, int] = {}
    if not inferred_effects_by_id:
        return out
    selected = _selected_perk_ids_by_deadline(engine, deadline)
    for perk_id in selected:
        effects = inferred_effects_by_id.get(int(perk_id))
        if effects is None:
            continue
        if effects.all_skills_bonus != 0:
            for av in SKILL_GOVERNING_ATTRIBUTE:
                out[int(av)] = out.get(int(av), 0) + int(effects.all_skills_bonus)
        for av, bonus in effects.per_skill_bonus.items():
            out[int(av)] = out.get(int(av), 0) + int(bonus)
    return out


def _effective_experience_multiplier(
    engine: BuildEngine,
    *,
    deadline: int,
    inferred_effects_by_id: dict[int, InferredSkillEffects] | None,
) -> float:
    if not inferred_effects_by_id:
        return 1.0
    selected = _selected_perk_ids_by_deadline(engine, deadline)
    mult = 1.0
    for perk_id in selected:
        effects = inferred_effects_by_id.get(int(perk_id))
        if effects is None or effects.experience_multiplier_factor is None:
            continue
        mult *= float(effects.experience_multiplier_factor)
    return mult


def _effective_damage_multiplier(
    engine: BuildEngine,
    *,
    deadline: int,
    inferred_effects_by_id: dict[int, InferredSkillEffects] | None,
) -> float:
    if not inferred_effects_by_id:
        return 1.0
    selected = _selected_perk_ids_by_deadline(engine, deadline)
    mult = 1.0
    for perk_id in selected:
        effects = inferred_effects_by_id.get(int(perk_id))
        if effects is None or effects.damage_multiplier_factor is None:
            continue
        mult *= float(effects.damage_multiplier_factor)
    return mult


def _effective_crit_chance_bonus(
    engine: BuildEngine,
    *,
    deadline: int,
    inferred_effects_by_id: dict[int, InferredSkillEffects] | None,
) -> float:
    if not inferred_effects_by_id:
        return 0.0
    selected = _selected_perk_ids_by_deadline(engine, deadline)
    bonus = 0.0
    for perk_id in selected:
        effects = inferred_effects_by_id.get(int(perk_id))
        if effects is None:
            continue
        bonus += float(effects.crit_chance_bonus_flat)
    return bonus


def _choose_best_max_skills_perk(
    engine: BuildEngine,
    *,
    level: int,
    target_level: int,
    available: set[int],
    pending_required: list[int],
    requirements: list[RequirementSpec],
    perks_by_id: dict[int, Perk],
    inferred_effects_by_id: dict[int, InferredSkillEffects],
    skill_books_by_av: dict[int, int],
) -> tuple[int, int | None, str] | None:
    best: tuple[int, int | None, str] | None = None
    best_score = 0.0
    for perk_id in sorted(available):
        effects = inferred_effects_by_id.get(int(perk_id))
        if effects is None or not effects.is_relevant:
            continue
        score = _score_max_skills_perk_action(
            engine,
            level=level,
            target_level=target_level,
            perk_id=int(perk_id),
            effects=effects,
            pending_required=pending_required,
            requirements=requirements,
            perks_by_id=perks_by_id,
            skill_books_by_av=skill_books_by_av,
            inferred_effects_by_id=inferred_effects_by_id,
        )
        if score is None:
            continue
        score_value, special_target, reason = score
        if score_value > best_score:
            best_score = score_value
            best = (int(perk_id), special_target, reason)
    return best


def _choose_requirement_support_perk(
    engine: BuildEngine,
    *,
    level: int,
    target_level: int,
    available: set[int],
    pending_required: list[int],
    requirements: list[RequirementSpec],
    perks_by_id: dict[int, Perk],
    inferred_effects_by_id: dict[int, InferredSkillEffects],
) -> tuple[int, int | None, str] | None:
    best: tuple[int, int | None, str] | None = None
    best_score = 0.0
    for perk_id in sorted(available):
        effects = inferred_effects_by_id.get(int(perk_id))
        if effects is None:
            continue
        score = 0.0
        special_target: int | None = None
        reasons: list[str] = []

        if effects.selectable_special_points > 0:
            target = _best_special_to_raise(
                engine,
                level=level,
                pending_required=pending_required,
                requirements=requirements,
                perks_by_id=perks_by_id,
                target_level=target_level,
            )
            if target is not None:
                current = int(engine.stats_at(level).effective_special.get(target, 0))
                if current < 10 and not _has_available_implant_for_special_target(
                    engine,
                    level=level,
                    target_av=int(target),
                    perks_by_id=perks_by_id,
                ):
                    score += float(10 - current)
                    special_target = target
                    reasons.append("Helps satisfy SPECIAL/perk gates.")

        if effects.experience_multiplier_factor is not None:
            for req in requirements:
                if req.kind != "experience_multiplier":
                    continue
                deadline = _requirement_deadline(req, target_level)
                target_pct = (
                    float(req.value_float)
                    if req.value_float is not None
                    else float(req.value if req.value is not None else 100)
                )
                current_pct = _effective_experience_multiplier(
                    engine,
                    deadline=deadline,
                    inferred_effects_by_id=inferred_effects_by_id,
                ) * 100.0
                projected_pct = current_pct * float(effects.experience_multiplier_factor)
                current_gap = max(0.0, target_pct - current_pct)
                projected_gap = max(0.0, target_pct - projected_pct)
                gain = max(0.0, current_gap - projected_gap)
                score += gain
                if gain > 0:
                    reasons.append(f"Improves XP multiplier toward {target_pct:g}%.")

        if effects.damage_multiplier_factor is not None:
            for req in requirements:
                if req.kind != "damage_multiplier":
                    continue
                deadline = _requirement_deadline(req, target_level)
                target_pct = (
                    float(req.value_float)
                    if req.value_float is not None
                    else float(req.value if req.value is not None else 100)
                )
                current_pct = _effective_damage_multiplier(
                    engine,
                    deadline=deadline,
                    inferred_effects_by_id=inferred_effects_by_id,
                ) * 100.0
                projected_pct = current_pct * float(effects.damage_multiplier_factor)
                current_gap = max(0.0, target_pct - current_pct)
                projected_gap = max(0.0, target_pct - projected_pct)
                gain = max(0.0, current_gap - projected_gap)
                score += gain
                if gain > 0:
                    reasons.append(f"Improves damage multiplier toward {target_pct:g}%.")

        if effects.crit_chance_bonus_flat > 0:
            for req in requirements:
                if req.kind != "crit_chance_bonus":
                    continue
                deadline = _requirement_deadline(req, target_level)
                target_val = (
                    float(req.value_float)
                    if req.value_float is not None
                    else float(req.value if req.value is not None else 0)
                )
                current_val = _effective_crit_chance_bonus(
                    engine,
                    deadline=deadline,
                    inferred_effects_by_id=inferred_effects_by_id,
                )
                projected_val = current_val + float(effects.crit_chance_bonus_flat)
                current_gap = max(0.0, target_val - current_val)
                projected_gap = max(0.0, target_val - projected_val)
                gain = max(0.0, current_gap - projected_gap)
                score += gain
                if gain > 0:
                    reasons.append(f"Improves crit bonus toward {target_val:g}.")

        if score <= 0:
            continue
        if score > best_score:
            best_score = score
            best = (
                int(perk_id),
                special_target,
                " ".join(reasons) if reasons else "Supports active requirements.",
            )
    return best


def _score_max_skills_perk_action(
    engine: BuildEngine,
    *,
    level: int,
    target_level: int,
    perk_id: int,
    effects: InferredSkillEffects,
    pending_required: list[int],
    requirements: list[RequirementSpec],
    perks_by_id: dict[int, Perk],
    skill_books_by_av: dict[int, int],
    inferred_effects_by_id: dict[int, InferredSkillEffects],
) -> tuple[float, int | None, str] | None:
    trial = engine.copy()
    try:
        trial.select_perk(level, perk_id)
    except ValueError:
        return None

    score = 0.0
    special_target: int | None = None
    reasons: list[str] = []
    remaining_levelups = max(0, target_level - level)
    if effects.skill_points_per_level_bonus > 0 and remaining_levelups > 0:
        gain = float(effects.skill_points_per_level_bonus * remaining_levelups)
        score += gain
        reasons.append(f"Projected +{gain:.0f} future skill points.")

    target_stats = trial.stats_at(target_level)
    for av in SKILL_GOVERNING_ATTRIBUTE:
        skill_val = int(target_stats.skills.get(int(av), 0))
        deficit = max(0, 100 - skill_val)
        if deficit <= 0:
            continue
        if effects.all_skills_bonus > 0:
            gain = float(min(deficit, effects.all_skills_bonus))
            score += gain
        bonus = int(effects.per_skill_bonus.get(int(av), 0))
        if bonus > 0:
            score += float(min(deficit, bonus))
    if effects.all_skills_bonus > 0:
        reasons.append(f"Flat +{effects.all_skills_bonus} all-skills bonus.")

    if effects.skill_book_points_bonus > 0:
        per_book_without = _effective_skill_book_points(
            engine,
            deadline=target_level,
            inferred_effects_by_id=inferred_effects_by_id,
        )
        per_book_with = _effective_skill_book_points(
            trial,
            deadline=target_level,
            inferred_effects_by_id=inferred_effects_by_id,
        )
        flat_bonuses = _effective_flat_skill_bonuses(
            trial,
            deadline=target_level,
            inferred_effects_by_id=inferred_effects_by_id,
        )
        deficits: dict[int, int] = {}
        for av in SKILL_GOVERNING_ATTRIBUTE:
            effective = int(target_stats.skills.get(int(av), 0)) + int(flat_bonuses.get(int(av), 0))
            deficits[int(av)] = max(0, 100 - effective)
        gain = _book_marginal_coverage_gain(
            deficits=deficits,
            books_by_av=skill_books_by_av,
            per_book_without=per_book_without,
            per_book_with=per_book_with,
        )
        score += gain
        if gain > 0:
            reasons.append(f"Books cover +{gain:.0f} extra skill points.")

    if effects.selectable_special_points > 0:
        target = _best_special_to_raise(
            trial,
            level=level,
            pending_required=pending_required,
            requirements=requirements,
            perks_by_id=perks_by_id,
            target_level=target_level,
        )
        if target is None:
            target = int(ActorValue.INTELLIGENCE)
        current = int(trial.stats_at(level).effective_special.get(target, 0))
        if current < 10:
            if _has_available_implant_for_special_target(
                engine,
                level=level,
                target_av=int(target),
                perks_by_id=perks_by_id,
            ):
                reasons.append("Implant can provide this SPECIAL point; preserve perk slot.")
                reason = " ".join(reasons) if reasons else "Highest projected max-skills gain."
                return score, special_target, reason
            try:
                trial.allocate_special_points(level, {target: 1})
                after = trial.stats_at(target_level).skills
                before = target_stats.skills
                gain = sum(
                    max(0, int(after.get(int(av), 0)) - int(before.get(int(av), 0)))
                    for av in SKILL_GOVERNING_ATTRIBUTE
                )
                score += float(gain)
                special_target = target
                if gain > 0:
                    reasons.append(f"SPECIAL allocation projects +{gain:.0f} skill value.")
            except ValueError:
                pass
    reason = " ".join(reasons) if reasons else "Highest projected max-skills gain."
    return score, special_target, reason


def _book_marginal_coverage_gain(
    *,
    deficits: dict[int, int],
    books_by_av: dict[int, int],
    per_book_without: int,
    per_book_with: int,
) -> float:
    """Projected extra covered skill points from improving book value."""
    if per_book_with <= per_book_without:
        return 0.0
    gain = 0.0
    for av, deficit in deficits.items():
        if deficit <= 0:
            continue
        books = max(0, int(books_by_av.get(int(av), 0)))
        if books <= 0:
            continue
        covered_without = min(deficit, books * per_book_without)
        covered_with = min(deficit, books * per_book_with)
        gain += float(max(0, covered_with - covered_without))
    return gain


_SKILL_NAME_ALIASES: dict[int, tuple[str, ...]] = {
    int(ActorValue.BARTER): ("barter",),
    int(ActorValue.ENERGY_WEAPONS): ("energy weapons",),
    int(ActorValue.EXPLOSIVES): ("explosives",),
    int(ActorValue.GUNS): ("guns",),
    int(ActorValue.LOCKPICK): ("lockpick", "lockpicking"),
    int(ActorValue.MEDICINE): ("medicine",),
    int(ActorValue.MELEE_WEAPONS): ("melee weapons", "melee"),
    int(ActorValue.REPAIR): ("repair",),
    int(ActorValue.SCIENCE): ("science",),
    int(ActorValue.SNEAK): ("sneak",),
    int(ActorValue.SPEECH): ("speech",),
    int(ActorValue.SURVIVAL): ("survival",),
    int(ActorValue.UNARMED): ("unarmed",),
}


def _infer_perk_skill_effects(
    perk: Perk,
    *,
    linked_spell_names_by_form: dict[int, str] | None = None,
    linked_spell_stat_bonuses_by_form: dict[int, dict[int, float]] | None = None,
) -> InferredSkillEffects:
    effects = InferredSkillEffects()
    _apply_structured_entry_effect_inference(
        perk,
        effects,
        linked_spell_names_by_form=linked_spell_names_by_form,
        linked_spell_stat_bonuses_by_form=linked_spell_stat_bonuses_by_form,
    )
    text = f"{perk.name} {perk.editor_id} {perk.description}".lower()
    _apply_skill_text_inference(text, effects)

    return effects


def _apply_skill_text_inference(text: str, effects: InferredSkillEffects) -> None:
    text_for_segments = text.replace(", but ", ". ").replace(" but ", ". ")
    # Skill points/level effects (e.g., Educated).
    m = re.search(r"(\d+)\s+(?:additional|more)\s+skill points?(?:\s+every level|\s+when you level up)?", text)
    if m:
        effects.skill_points_per_level_bonus = max(
            effects.skill_points_per_level_bonus, int(m.group(1))
        )

    # Book effects (e.g., Comprehension).
    if "double the bonus from skill books" in text:
        effects.skill_book_points_bonus = max(effects.skill_book_points_bonus, 1)
    word_to_num = {"one": 1, "two": 2, "three": 3}
    m = re.search(
        r"(one|two|three|\d+)\s+additional skill points?\s+when reading (?:skill )?books",
        text,
    )
    if m:
        val_raw = m.group(1)
        val = word_to_num.get(val_raw, int(val_raw) if val_raw.isdigit() else 0)
        effects.skill_book_points_bonus = max(effects.skill_book_points_bonus, val)

    # All-skills bonuses (e.g., Skilled).
    m = re.search(r"([+-])\s*(\d+)\s+to\s+(?:all\s+)?skills", text)
    if m:
        sign = -1 if m.group(1) == "-" else 1
        effects.all_skills_bonus = sign * int(m.group(2))

    # Per-skill flat bonuses.
    # Handle grouped wording like:
    # "gain 5 points to Barter, Medicine ... but lose 5 points to Energy Weapons ..."
    for m in re.finditer(r"(gain|gains|add|adds)\s+(\d+)\s+points?\s+to\s+([^.;]+)", text_for_segments):
        _apply_segment_skill_bonus(effects, segment=m.group(3), amount=int(m.group(2)))
    for m in re.finditer(r"(lose|loses)\s+(\d+)\s+points?\s+to\s+([^.;]+)", text_for_segments):
        _apply_segment_skill_bonus(effects, segment=m.group(3), amount=-int(m.group(2)))
    for m in re.finditer(r"([+-])\s*(\d+)\s+to\s+([^.;]+)", text_for_segments):
        sign = -1 if m.group(1) == "-" else 1
        _apply_segment_skill_bonus(effects, segment=m.group(3), amount=sign * int(m.group(2)))

    for av, aliases in _SKILL_NAME_ALIASES.items():
        for alias in aliases:
            m = re.search(rf"([+-])\s*(\d+)\s+to\s+{re.escape(alias)}", text)
            if not m:
                continue
            sign = -1 if m.group(1) == "-" else 1
            val = sign * int(m.group(2))
            effects.per_skill_bonus[av] = val

    # Selectable SPECIAL bonuses (e.g., Intense Training-like effects).
    if (
        "special" in text
        and "increase" in text
        and "by 1" in text
        and ("one of your special" in text or "choose one" in text)
    ):
        effects.selectable_special_points = 1

    # XP multiplier effects.
    m = re.search(r"(\d+)\s*%\s+more experience", text)
    if m:
        factor = 1.0 + (float(m.group(1)) / 100.0)
        prev = effects.experience_multiplier_factor
        effects.experience_multiplier_factor = factor if prev is None else prev * factor
    m = re.search(r"(\d+)\s*%\s+(?:less|penalty).*experience", text)
    if m:
        factor = max(0.0, 1.0 - (float(m.group(1)) / 100.0))
        prev = effects.experience_multiplier_factor
        effects.experience_multiplier_factor = factor if prev is None else prev * factor

    # Generic outgoing damage multipliers.
    m = re.search(r"(\d+)\s*%\s+more damage", text)
    if m:
        factor = 1.0 + (float(m.group(1)) / 100.0)
        prev = effects.damage_multiplier_factor
        effects.damage_multiplier_factor = factor if prev is None else prev * factor

    # Flat critical chance bonuses.
    m = re.search(r"(\d+)\s+extra points?\s+of\s+critical chance", text)
    if m:
        effects.crit_chance_bonus_flat += float(m.group(1))
    m = re.search(r"\+(\d+)\s*%\s+(?:chance to )?(?:get )?a critical hit", text)
    if m:
        effects.crit_chance_bonus_flat += float(m.group(1))


def _apply_structured_entry_effect_inference(
    perk: Perk,
    effects: InferredSkillEffects,
    *,
    linked_spell_names_by_form: dict[int, str] | None = None,
    linked_spell_stat_bonuses_by_form: dict[int, dict[int, float]] | None = None,
) -> None:
    # Parse well-known entry-point effect patterns from PRKE/EPFT/EPFD blocks.
    # This avoids perk-name hardcoding and keeps MAX SKILLS behavior data-driven.
    for block in perk.entry_point_effects:
        epfd_val = _decode_epfd_float(block.epfd, block.epft)
        for payload in block.data_payloads:
            if len(payload) == 3 and block.entry_point == 2:
                # Common perk-entry form: [function_id, op, arg]
                function_id = payload[0]
                if function_id == 10 and epfd_val is not None:
                    # e.g. Educated (+N skill points/level)
                    effects.skill_points_per_level_bonus = max(
                        effects.skill_points_per_level_bonus,
                        max(0, int(round(epfd_val))),
                    )
                elif function_id == 11 and epfd_val is not None:
                    # e.g. Comprehension (extra skill-book points)
                    effects.skill_book_points_bonus = max(
                        effects.skill_book_points_bonus,
                        max(0, int(round(epfd_val))),
                    )
                elif function_id == 9 and epfd_val is not None and epfd_val > 0:
                    # e.g. Swift Learner / Well Rested / Skilled XP effects.
                    factor = float(epfd_val)
                    prev = effects.experience_multiplier_factor
                    if prev is None:
                        effects.experience_multiplier_factor = factor
                    else:
                        effects.experience_multiplier_factor = prev * factor
                elif function_id == 0 and epfd_val is not None and epfd_val > 0:
                    # Common damage-multiplier entry point family.
                    factor = float(epfd_val)
                    if 0.1 <= factor <= 10.0:
                        prev = effects.damage_multiplier_factor
                        effects.damage_multiplier_factor = factor if prev is None else prev * factor
            elif len(payload) == 8 and block.entry_point == 0:
                # Intense-Training-like selectable SPECIAL boosts appear as
                # entry-point 0 with rank-indexed payloads.
                key = payload[4]
                if 0x65 <= key <= 0x6E:
                    effects.selectable_special_points = max(effects.selectable_special_points, 1)
            elif (
                len(payload) == 4
                and block.entry_point == 1
                and (linked_spell_names_by_form or linked_spell_stat_bonuses_by_form)
            ):
                form_id = struct.unpack("<I", payload)[0]
                if linked_spell_names_by_form:
                    spell_name = linked_spell_names_by_form.get(int(form_id), "")
                    if spell_name:
                        _apply_skill_text_inference(spell_name.lower(), effects)
                if linked_spell_stat_bonuses_by_form:
                    bonuses = linked_spell_stat_bonuses_by_form.get(int(form_id), {})
                    for av, val in bonuses.items():
                        iav = int(av)
                        if iav in SKILL_GOVERNING_ATTRIBUTE:
                            effects.per_skill_bonus[iav] = (
                                effects.per_skill_bonus.get(iav, 0) + int(round(float(val)))
                            )
                    crit = float(bonuses.get(14, 0.0))
                    if crit > 0:
                        effects.crit_chance_bonus_flat += crit


def _decode_epfd_float(epfd: bytes | None, epft: int | None) -> float | None:
    if epfd is None:
        return None
    if len(epfd) == 4 and (epft in (None, 1)):
        try:
            return float(struct.unpack("<f", epfd)[0])
        except struct.error:
            return None
    return None


def _apply_segment_skill_bonus(effects: InferredSkillEffects, *, segment: str, amount: int) -> None:
    seg = segment.lower()
    for av, aliases in _SKILL_NAME_ALIASES.items():
        if any(alias in seg for alias in aliases):
            effects.per_skill_bonus[av] = int(amount)


def _books_needed(deficit: int, per_book: int) -> int:
    if deficit <= 0:
        return 0
    if per_book <= 1:
        return deficit
    return (deficit + per_book - 1) // per_book


def _rebalance_max_skills_with_book_constraints(
    engine: BuildEngine,
    *,
    target_level: int,
    skill_books_by_av: dict[int, int],
    inferred_effects_by_id: dict[int, InferredSkillEffects] | None,
) -> None:
    """Shift allocated points from over-covered skills to book-starved skills."""
    max_iters = 512
    for _ in range(max_iters):
        stats = engine.stats_at(target_level)
        flat = _effective_flat_skill_bonuses(
            engine,
            deadline=target_level,
            inferred_effects_by_id=inferred_effects_by_id,
        )
        per_book = _effective_skill_book_points(
            engine,
            deadline=target_level,
            inferred_effects_by_id=inferred_effects_by_id,
        )

        deficits: dict[int, int] = {}
        cushion: dict[int, int] = {}
        for av in SKILL_GOVERNING_ATTRIBUTE:
            raw = int(stats.skills.get(int(av), 0))
            effective = raw + int(flat.get(int(av), 0))
            books = max(0, int(skill_books_by_av.get(int(av), 0)))
            max_cover = effective + books * per_book
            deficits[int(av)] = max(0, 100 - max_cover)
            cushion[int(av)] = max(0, max_cover - 100)

        need = [av for av, gap in deficits.items() if gap > 0]
        if not need:
            return
        recv = max(need, key=lambda av: (deficits[av], -av))

        donor: int | None = None
        donor_level: int | None = None
        donor_score = -1
        for lv in sorted(engine.state.level_plans.keys(), reverse=True):
            plan = engine.state.level_plans[lv]
            for av, pts in plan.skill_points.items():
                iav = int(av)
                if iav not in SKILL_GOVERNING_ATTRIBUTE or iav == recv or pts <= 0:
                    continue
                if cushion.get(iav, 0) <= 0:
                    continue
                if cushion[iav] > donor_score:
                    donor = iav
                    donor_level = int(lv)
                    donor_score = cushion[iav]

        if donor is None or donor_level is None:
            return

        current = dict(engine.state.level_plans[donor_level].skill_points)
        if current.get(donor, 0) <= 0:
            return
        current[donor] = current.get(donor, 0) - 1
        if current[donor] <= 0:
            del current[donor]
        current[recv] = current.get(recv, 0) + 1
        try:
            engine.allocate_skill_points(donor_level, current)
        except ValueError:
            return


def _threshold(operator: str, value: int) -> int | None:
    if operator == ">=":
        return int(value)
    if operator == ">":
        return int(value) + 1
    if operator == "==":
        return int(value)
    return None


def _compare(actual: int, operator: str, target: int) -> bool:
    if operator == ">=":
        return actual >= target
    if operator == ">":
        return actual > target
    if operator == "==":
        return actual == target
    if operator == "<=":
        return actual <= target
    if operator == "<":
        return actual < target
    return False
