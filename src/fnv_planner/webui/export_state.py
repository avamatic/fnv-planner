"""Export planner state for the web UI runtime."""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fnv_planner.models.constants import ACTOR_VALUE_NAMES
from fnv_planner.models.item import Armor, Weapon
from fnv_planner.ui.bootstrap import BuildSession, bootstrap_default_session
from fnv_planner.ui.controllers.build_controller import BuildController
from fnv_planner.ui.controllers.library_controller import LibraryController
from fnv_planner.ui.controllers.progression_controller import ProgressionController
from fnv_planner.ui.state import UiState


def _stats_payload(stats) -> dict[str, Any]:
    return {
        "hit_points": int(stats.hit_points),
        "action_points": int(stats.action_points),
        "carry_weight": float(stats.carry_weight),
        "crit_chance": float(stats.crit_chance),
        "crit_damage_potential": float(stats.crit_damage_potential),
        "melee_damage": float(stats.melee_damage),
        "unarmed_damage": float(stats.unarmed_damage),
        "poison_resistance": float(stats.poison_resistance),
        "rad_resistance": float(stats.rad_resistance),
        "skill_points_per_level": int(stats.skill_points_per_level),
        "companion_nerve": float(stats.companion_nerve),
        "max_level": int(stats.max_level),
    }


def sync_progression_from_build(
    build: BuildController,
    progression: ProgressionController,
) -> None:
    progression.set_anytime_perks(build.anytime_desired_perk_labels())
    progression.set_perk_reasons(build.perk_reasons())
    progression.set_skill_book_usage(
        build.needed_skill_books(),
        build.total_skill_books(),
        build.skill_book_rows(),
        build.skill_book_usage_by_level(),
        build.skill_book_points_by_level(),
    )
    progression.set_zero_cost_perks_by_level(build.zero_cost_perk_events_by_level())
    progression.set_implant_usage_by_level(build.implant_points_by_level())
    progression.set_flat_skill_bonus_by_level(build.flat_skill_bonuses_by_level())


def _item_kind(item: Armor | Weapon | None) -> str:
    if isinstance(item, Armor):
        return "armor"
    if isinstance(item, Weapon):
        return "weapon"
    return "unknown"


def _item_effects(library: LibraryController, form_id: int) -> list[str]:
    item = library.get_item(int(form_id))
    if item is None:
        return []
    rows: list[str] = []
    for effect in item.stat_effects:
        rows.append(library.format_effect(effect))
    return rows


def build_webui_state_from_controllers(
    *,
    session: BuildSession,
    state: UiState,
    build: BuildController,
    progression: ProgressionController,
    library: LibraryController,
) -> dict[str, Any]:
    """Build a current snapshot from live controllers."""
    sync_progression_from_build(build, progression)
    library.refresh()

    now, target, delta, valid = build.summary()
    feasible, feasibility_message = build.feasibility_warning()

    progression_rows = []
    for snap in progression.progression_rows():
        effective_skills = progression.effective_skills_for_level(snap.level, snap.stats.skills)
        progression_rows.append(
            {
                "level": int(snap.level),
                "perk_id": int(snap.perk_id) if snap.perk_id is not None else None,
                "perk_label": progression.perk_label_for_level(snap.level, snap.perk_id),
                "perk_reason": progression.perk_reason_for_level(snap.level),
                "spent_skill_points": int(snap.spent_skill_points),
                "unspent_skill_points": int(snap.unspent_skill_points),
                "allocation_label": progression.skill_allocation_label_for_level(snap.level),
                "stats": _stats_payload(snap.stats),
                "skills": {
                    ACTOR_VALUE_NAMES.get(int(av), f"AV{av}"): int(val)
                    for av, val in sorted(effective_skills.items())
                    if 32 <= int(av) <= 45
                },
                "event_skill_books": progression.skill_books_between_levels_label(
                    max(1, snap.level - 1), snap.level
                ),
                "event_implants": progression.implants_between_levels_label(
                    max(1, snap.level - 1), snap.level
                ),
                "event_zero_cost": progression.zero_cost_perks_between_levels_label(
                    max(1, snap.level - 1), snap.level
                ),
            }
        )

    diagnostics = [asdict(d) for d in build.diagnostics()]
    request_rows = build.priority_request_rows()
    request_entries = build.priority_request_payloads()
    selected_perk_ids = build.selected_perk_ids()
    selected_trait_ids = build.selected_trait_ids()
    selected_tagged_skill_ids = build.selected_tagged_skill_ids()

    actor_value_controls = []
    for av, name in build.actor_value_options():
        actor_value_controls.append(
            {
                "actor_value": int(av),
                "name": str(name),
                "max": int(build.actor_value_request_max(int(av))),
                "description": build.actor_value_description(int(av)),
            }
        )

    special_used, special_remaining = build.special_totals()

    perk_rows = build.perk_rows("")
    perk_statuses = build.perk_request_statuses(sorted(int(v) for v in selected_perk_ids))
    perk_payload = [
        {
            "id": int(perk_id),
            "name": name,
            "category": category,
            "selected": bool(is_selected),
            "request_status": str(perk_statuses.get(int(perk_id), {}).get("status", "none")),
            "request_status_reason": str(perk_statuses.get(int(perk_id), {}).get("reason", "")),
        }
        for perk_id, name, category, is_selected in perk_rows
    ]

    equipped_by_slot = {
        int(slot): int(form_id)
        for slot, form_id in build.engine.state.equipment.items()
    }
    gear_payload = []
    for item in library.catalog_items():
        equipped_form = equipped_by_slot.get(int(item.slot))
        gear_payload.append(
            {
                "id": int(item.form_id),
                "kind": str(item.kind),
                "name": str(item.name),
                "slot": int(item.slot),
                "value": int(item.value),
                "weight": float(item.weight),
                "conditional_effects": int(item.conditional_effects),
                "excluded_conditional_effects": int(item.excluded_conditional_effects),
                "equipped": bool(equipped_form == int(item.form_id)),
            }
        )

    equipped_payload = []
    for slot, form_id, label in library.equipped_slots():
        item = library.get_item(int(form_id))
        equipped_payload.append(
            {
                "slot": int(slot),
                "form_id": int(form_id),
                "name": str(label),
                "kind": _item_kind(item),
                "effects": _item_effects(library, int(form_id)),
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "app": {
            "name": state.build_name,
            "plugin_mode": state.plugin_source.mode,
            "target_level": int(state.target_level),
            "max_level": int(state.max_level),
            "game_variant": state.game_variant,
            "banner_title": state.banner_title,
        },
        "build": {
            "valid": bool(valid),
            "feasible": bool(feasible),
            "feasibility_message": str(feasibility_message),
            "current_level": int(build.current_level),
            "now": _stats_payload(now),
            "target": _stats_payload(target),
            "delta": {k: float(v) for k, v in delta.items()},
            "special_rows": [
                {"actor_value": int(av), "name": name, "value": int(value)}
                for av, name, value in build.special_rows()
            ],
            "special": {
                "budget": int(build.special_budget),
                "min": int(build.special_min),
                "max": int(build.special_max),
                "used": int(special_used),
                "remaining": int(special_remaining),
            },
            "meta": {
                "fill_perk_slots": True,
                "max_skills": any(req["kind"] == "max_skills" for req in request_entries),
                "max_crit": any(req["kind"] == "max_crit" for req in request_entries),
                "max_crit_damage": any(req["kind"] == "max_crit_damage" for req in request_entries),
            },
            "request_controls": {
                "actor_values": actor_value_controls,
                "traits": [
                    {
                        "id": int(trait_id),
                        "name": name,
                        "selected": int(trait_id) in selected_trait_ids,
                    }
                    for trait_id, name in build.trait_options()
                ],
                "tagged_skills": [
                    {
                        "actor_value": int(av),
                        "name": name,
                        "selected": int(av) in selected_tagged_skill_ids,
                    }
                    for av, name in build.tagged_skill_options()
                ],
            },
            "requests": [
                {"index": int(i), "text": text}
                for i, text in request_rows
            ],
            "request_entries": request_entries,
            "selected_traits": [
                {"name": name, "source": source}
                for name, source in build.selected_traits_rows()
            ],
            "selected_tagged_skills": [
                {"name": name, "source": source}
                for name, source in build.selected_tagged_skills_rows()
            ],
            "selected_perks": [
                {"name": name, "level": int(level), "source": source}
                for name, level, source in build.selected_perks_rows()
            ],
            "skill_books": {
                "needed": int(build.needed_skill_books()),
                "available": int(build.total_skill_books()),
                "rows": [
                    {"skill": name, "needed": int(needed), "available": int(available)}
                    for name, needed, available in build.skill_book_rows()
                ],
            },
            "perk_rationale": list(build.perk_reason_rows()),
            "book_dependency_warning": build.book_dependency_warning(),
            "diagnostics": diagnostics,
        },
        "progression": {
            "rows": progression_rows,
            "anytime_perks": list(progression.anytime_perk_labels or []),
            "skill_books_summary": progression.skill_books_summary(),
        },
        "library": {
            "perks": perk_payload,
            "selected_perk_ids": [int(v) for v in sorted(selected_perk_ids)],
            "gear": gear_payload,
            "equipped": equipped_payload,
        },
    }


def build_webui_state(
    *,
    include_max_skills: bool = True,
    include_max_crit: bool = True,
    include_max_crit_damage: bool = False,
    plugin_paths: list[Path] | None = None,
) -> dict[str, Any]:
    """Build a deterministic snapshot for reviewable web UI rendering."""
    session, state = bootstrap_default_session(plugin_paths)

    build = BuildController(
        engine=session.engine,
        ui_model=session.ui_model,
        perks=session.perks,
        challenge_perk_ids=session.challenge_perk_ids,
        skill_books_by_av=session.skill_books_by_av,
        linked_spell_names_by_form=session.linked_spell_names_by_form,
        linked_spell_stat_bonuses_by_form=session.linked_spell_stat_bonuses_by_form,
        state=state,
        av_descriptions_by_av=session.av_descriptions_by_av,
        armors_by_id=session.armors,
        weapons_by_id=session.weapons,
        current_level=1,
    )
    progression = ProgressionController(
        engine=session.engine,
        ui_model=session.ui_model,
        perks=session.perks,
        state=state,
        av_descriptions_by_av=session.av_descriptions_by_av,
    )
    library = LibraryController(
        engine=session.engine,
        ui_model=session.ui_model,
        armors=session.armors,
        weapons=session.weapons,
        state=state,
    )

    if include_max_skills:
        build.add_max_skills_request()
    if include_max_crit:
        build.add_max_crit_request()
    if include_max_crit_damage:
        build.add_max_crit_damage_request()

    return build_webui_state_from_controllers(
        session=session,
        state=state,
        build=build,
        progression=progression,
        library=library,
    )
