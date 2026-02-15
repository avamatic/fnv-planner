"""Plan a level-by-level build from goal and starting-condition JSON.

Usage examples:
    python -m scripts.plan_build --goal-file goal.json
    python -m scripts.plan_build --goal-json '{"required_perks":[4096],"target_level":20}'
    python -m scripts.plan_build --goal-file goal.json --start-file start.json --json
    python -m scripts.plan_build --goal-file goal.json --esm /path/to/FalloutNV.esm
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fnv_planner.engine.build_engine import BuildEngine
from fnv_planner.graph.dependency_graph import DependencyGraph
from fnv_planner.models.constants import ACTOR_VALUE_NAMES
from fnv_planner.models.game_settings import GameSettings
from fnv_planner.models.perk import Perk
from fnv_planner.optimizer.planner import PlanResult, plan_build
from fnv_planner.optimizer.specs import GoalSpec, RequirementSpec, StartingConditions
from fnv_planner.parser.book_stats import (
    placed_skill_book_copies_by_actor_value,
    skill_books_by_actor_value,
)
from fnv_planner.parser.item_parser import parse_all_books
from fnv_planner.parser.perk_classification import detect_challenge_perk_ids
from fnv_planner.parser.perk_parser import parse_all_perks
from fnv_planner.parser.plugin_merge import (
    effective_vanilla_level_cap,
    has_non_base_level_cap_override,
    load_plugin_bytes,
    parse_records_merged,
    resolve_plugins_for_cli,
)
from fnv_planner.parser.spell_parser import (
    linked_spell_names_by_form,
    linked_spell_stat_bonuses_by_form,
)


DEFAULT_ESM = Path(
    "/home/am/.local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm"
)

NAME_TO_AV = {name.lower(): av for av, name in ACTOR_VALUE_NAMES.items()}


def _parse_int_like(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("bool is not a valid integer value")
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        return int(value.strip(), 0)
    raise ValueError(f"Expected integer-like value, got: {value!r}")


def _parse_av(value: Any) -> int:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text, 0)
        except ValueError:
            lowered = text.lower().replace("_", " ")
            if lowered in NAME_TO_AV:
                return int(NAME_TO_AV[lowered])
    raise ValueError(f"Unknown actor value: {value!r}")


def _load_json_arg(raw_json: str | None, file_path: Path | None) -> dict[str, Any]:
    if raw_json is not None:
        payload = json.loads(raw_json)
    elif file_path is not None:
        payload = json.loads(file_path.read_text())
    else:
        return {}
    if not isinstance(payload, dict):
        raise ValueError("JSON payload must be an object")
    return payload


def _json_safe(value: Any) -> Any:
    """Recursively normalize values for JSON serialization."""
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, set):
        try:
            ordered = sorted(value)
        except TypeError:
            ordered = sorted(value, key=repr)
        return [_json_safe(v) for v in ordered]
    return value


def _goal_from_dict(data: dict[str, Any]) -> GoalSpec:
    required = [_parse_int_like(v) for v in data.get("required_perks", [])]
    skill_books_raw = data.get("skill_books_by_av")
    skill_books_by_av: dict[int, int] = {}
    if isinstance(skill_books_raw, dict):
        skill_books_by_av = {_parse_av(k): _parse_int_like(v) for k, v in skill_books_raw.items()}
    requirements: list[RequirementSpec] = []
    req_raw = data.get("requirements", [])
    if isinstance(req_raw, list):
        for entry in req_raw:
            if not isinstance(entry, dict):
                raise ValueError("Each requirements entry must be an object")
            kind = str(entry.get("kind", "")).strip().lower()
            if kind == "actor_value":
                requirements.append(
                    RequirementSpec(
                        kind="actor_value",
                        priority=_parse_int_like(entry.get("priority", 100)),
                        reason=str(entry.get("reason", "")),
                        by_level=(
                            _parse_int_like(entry["by_level"])
                            if "by_level" in entry and entry["by_level"] is not None
                            else None
                        ),
                        actor_value=_parse_av(entry["actor_value"]),
                        operator=str(entry.get("operator", ">=")),
                        value=_parse_int_like(entry["value"]),
                    )
                )
                continue
            if kind == "perk":
                requirements.append(
                    RequirementSpec(
                        kind="perk",
                        priority=_parse_int_like(entry.get("priority", 100)),
                        reason=str(entry.get("reason", "")),
                        by_level=(
                            _parse_int_like(entry["by_level"])
                            if "by_level" in entry and entry["by_level"] is not None
                            else None
                        ),
                        perk_id=_parse_int_like(entry["perk_id"]),
                        perk_rank=_parse_int_like(entry.get("perk_rank", 1)),
                    )
                )
                continue
            if kind == "trait":
                requirements.append(
                    RequirementSpec(
                        kind="trait",
                        priority=_parse_int_like(entry.get("priority", 100)),
                        reason=str(entry.get("reason", "")),
                        by_level=(
                            _parse_int_like(entry["by_level"])
                            if "by_level" in entry and entry["by_level"] is not None
                            else None
                        ),
                        trait_id=_parse_int_like(entry["trait_id"]),
                    )
                )
                continue
            if kind == "max_skills":
                requirements.append(
                    RequirementSpec(
                        kind="max_skills",
                        priority=_parse_int_like(entry.get("priority", 100)),
                        reason=str(entry.get("reason", "")),
                        by_level=(
                            _parse_int_like(entry["by_level"])
                            if "by_level" in entry and entry["by_level"] is not None
                            else None
                        ),
                    )
                )
                continue
            if kind in {"experience_multiplier", "damage_multiplier", "crit_chance_bonus"}:
                raw_value = entry.get("value_float", entry.get("value"))
                if raw_value is None:
                    raise ValueError(f"{kind} requires value/value_float")
                value_float = float(raw_value)
                requirements.append(
                    RequirementSpec(
                        kind=kind,
                        priority=_parse_int_like(entry.get("priority", 100)),
                        reason=str(entry.get("reason", "")),
                        by_level=(
                            _parse_int_like(entry["by_level"])
                            if "by_level" in entry and entry["by_level"] is not None
                            else None
                        ),
                        operator=str(entry.get("operator", ">=")),
                        value_float=value_float,
                    )
                )
                continue
            raise ValueError(f"Unsupported requirement kind: {entry.get('kind')!r}")

    target_level = data.get("target_level")
    maximize_skills = bool(data.get("maximize_skills", True))
    fill_perk_slots = bool(data.get("fill_perk_slots", False))
    return GoalSpec(
        required_perks=required,
        requirements=requirements,
        skill_books_by_av=skill_books_by_av,
        target_level=(_parse_int_like(target_level) if target_level is not None else None),
        maximize_skills=maximize_skills,
        fill_perk_slots=fill_perk_slots,
    )


def _starting_from_dict(data: dict[str, Any]) -> StartingConditions:
    special_raw = data.get("special")
    special: dict[int, int] | None = None
    if isinstance(special_raw, dict):
        special = {_parse_av(k): _parse_int_like(v) for k, v in special_raw.items()}

    tags_raw = data.get("tagged_skills")
    tagged_skills: set[int] | None = None
    if isinstance(tags_raw, list):
        tagged_skills = {_parse_av(v) for v in tags_raw}

    traits_raw = data.get("traits")
    traits: list[int] | None = None
    if isinstance(traits_raw, list):
        traits = [_parse_int_like(v) for v in traits_raw]

    equip_raw = data.get("equipment")
    equipment: dict[int, int] | None = None
    if isinstance(equip_raw, dict):
        equipment = {_parse_int_like(slot): _parse_int_like(form) for slot, form in equip_raw.items()}

    return StartingConditions(
        name=data.get("name"),
        sex=(_parse_int_like(data["sex"]) if "sex" in data else None),
        special=special,
        tagged_skills=tagged_skills,
        traits=traits,
        equipment=equipment,
        target_level=(
            _parse_int_like(data["target_level"]) if "target_level" in data else None
        ),
    )


def _render_text_result(
    result: PlanResult,
    *,
    engine: BuildEngine,
    perks_by_id: dict[int, Perk],
) -> str:
    lines: list[str] = []
    lines.append(f"success: {'yes' if result.success else 'no'}")
    lines.append(f"target level: {engine.state.target_level}")
    if result.selected_required_perks:
        chosen = ", ".join(f"{pid:#x}" for pid in result.selected_required_perks)
        lines.append(f"selected required perks: {chosen}")
    if result.missing_required_perks:
        missing = ", ".join(f"{pid:#x}" for pid in result.missing_required_perks)
        lines.append(f"missing required perks: {missing}")
    if result.skill_books_used:
        books = ", ".join(f"{av}:{count}" for av, count in sorted(result.skill_books_used.items()))
        lines.append(f"skill books used: {books}")
    if result.perk_selection_reasons:
        lines.append("perk rationale:")
        for lv in sorted(result.perk_selection_reasons):
            lines.append(f"  - L{lv}: {result.perk_selection_reasons[lv]}")
    if result.unmet_requirements:
        lines.append("unmet requirements:")
        lines.extend(f"  - {msg}" for msg in result.unmet_requirements)
    if result.messages:
        lines.append("messages:")
        lines.extend(f"  - {msg}" for msg in result.messages)

    lines.append("")
    lines.append("plan:")
    for lv in range(2, engine.state.target_level + 1):
        plan = engine.state.level_plans.get(lv)
        if plan is None:
            lines.append(f"  L{lv:>2}: (missing level plan)")
            continue
        perk = "-"
        if plan.perk is not None:
            perk_meta = perks_by_id.get(plan.perk)
            if perk_meta is None:
                perk = f"{plan.perk:#x}"
            else:
                perk = f"{perk_meta.name} ({plan.perk:#x})"
        spent = sum(plan.skill_points.values())
        unspent = engine.unspent_skill_points_at(lv)
        skills = ", ".join(f"{av}:{pts}" for av, pts in sorted(plan.skill_points.items()))
        lines.append(
            f"  L{lv:>2}: perk={perk:<28} spent={spent:>2} unspent={unspent:>2} "
            f"skills=[{skills}]"
        )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Plan a build from GoalSpec JSON")
    parser.add_argument(
        "--esm",
        type=Path,
        action="append",
        help="Plugin path; repeat in load order (last wins).",
    )
    goal_group = parser.add_mutually_exclusive_group(required=True)
    goal_group.add_argument("--goal-file", type=Path, help="Path to GoalSpec JSON file.")
    goal_group.add_argument("--goal-json", type=str, help="Inline GoalSpec JSON object.")

    start_group = parser.add_mutually_exclusive_group(required=False)
    start_group.add_argument("--start-file", type=Path, help="Path to StartingConditions JSON file.")
    start_group.add_argument("--start-json", type=str, help="Inline StartingConditions JSON object.")

    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output.")
    args = parser.parse_args()

    goal_payload = _load_json_arg(args.goal_json, args.goal_file)
    start_payload = _load_json_arg(args.start_json, args.start_file)
    goal = _goal_from_dict(goal_payload)
    starting = _starting_from_dict(start_payload)

    try:
        esm_paths, missing, _is_explicit = resolve_plugins_for_cli(args.esm, DEFAULT_ESM)
    except FileNotFoundError as exc:
        print(f"Warning: {exc}")
        esm_paths = []
        missing = []

    if missing:
        print("Warning: some default vanilla plugins are missing and will be skipped:")
        for p in missing:
            print(f"  - {p.name}")

    if esm_paths:
        print(f"Loading plugins: {', '.join(str(p) for p in esm_paths)}")
        plugin_datas = load_plugin_bytes(esm_paths)
        gmst = GameSettings.from_plugins(plugin_datas)
        if not gmst._values:
            print("Warning: GMST GRUP not found in provided plugins; using vanilla defaults.")
            gmst = GameSettings.defaults()
        else:
            has_override = has_non_base_level_cap_override(esm_paths, plugin_datas)
            gmst._values["iMaxCharacterLevel"] = effective_vanilla_level_cap(
                esm_paths,
                gmst.get_int("iMaxCharacterLevel", 50),
                has_non_base_cap_override=has_override,
            )
        perks = parse_records_merged(plugin_datas, parse_all_perks, missing_group_ok=True)
        challenge_perk_ids = detect_challenge_perk_ids(plugin_datas, perks)
        books = parse_records_merged(plugin_datas, parse_all_books, missing_group_ok=True)
        books_by_av = placed_skill_book_copies_by_actor_value(plugin_datas, books)
        if not books_by_av:
            books_by_av = skill_books_by_actor_value(books)
        if not goal.skill_books_by_av:
            goal.skill_books_by_av = books_by_av
        if books_by_av:
            print(f"Detected skill books in plugins: {sum(books_by_av.values())}")
        linked_spells = linked_spell_names_by_form(plugin_datas)
        linked_spell_bonuses = linked_spell_stat_bonuses_by_form(plugin_datas)
    else:
        gmst = GameSettings.defaults()
        perks = []
        challenge_perk_ids = set()
        linked_spells = {}
        linked_spell_bonuses = {}

    graph = DependencyGraph.build(perks)
    base_engine = BuildEngine.new_build(gmst, graph)
    perks_by_id = {p.form_id: p for p in perks}
    result = plan_build(
        base_engine,
        goal,
        starting=starting,
        perks_by_id=perks_by_id,
        challenge_perk_ids=challenge_perk_ids,
        linked_spell_names_by_form=linked_spells,
        linked_spell_stat_bonuses_by_form=linked_spell_bonuses,
    )
    solved_engine = BuildEngine.from_state(result.state, gmst, graph)

    if args.json:
        payload = {
            "success": result.success,
            "selected_required_perks": result.selected_required_perks,
            "missing_required_perks": result.missing_required_perks,
            "unmet_requirements": result.unmet_requirements,
            "skill_books_used": result.skill_books_used,
            "perk_selection_reasons": result.perk_selection_reasons,
            "messages": result.messages,
            "state": asdict(result.state),
        }
        print(json.dumps(_json_safe(payload), indent=2))
        return

    print(_render_text_result(result, engine=solved_engine, perks_by_id=perks_by_id))


if __name__ == "__main__":
    main()
