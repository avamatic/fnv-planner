"""Dump items from FalloutNV.esm with resolved stat effects.

Usage:
    python -m scripts.dump_items [--esm PATH] [--armor] [--weapons]
                                 [--consumables] [--books] [--playable-only]

If no category flags are given, all categories are shown.
"""

import argparse
import json
from pathlib import Path
from collections import Counter

from fnv_planner.parser.effect_resolver import EffectResolver
from fnv_planner.parser.item_parser import (
    parse_all_armors,
    parse_all_books,
    parse_all_consumables,
    parse_all_weapons,
)
from fnv_planner.models.game_settings import GameSettings
from fnv_planner.parser.plugin_merge import (
    is_missing_grup_error,
    load_plugin_bytes,
    parse_records_merged,
    resolve_plugins_for_cli,
)


DEFAULT_ESM = Path(
    "/home/am/.local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm"
)


def format_effects(effects) -> str:
    """Format stat effects with duration and context (enemy vs player).

    Format:
    - Timed hostile effects: [effect/s*duration]{Enemy}
    - Timed player effects: [effect*duration]{Player}
    - Instant/permanent: [effect]{Enemy/Player}
    - DoT: [-2 Health/s*10s]{Enemy}
    - Instant: [-50 Health]{Enemy}
    - Permanent buff: [+1 Luck]{Player}
    - Temporary buff: [+1 Intelligence*240s]{Player}
    """
    if not effects:
        return ""

    parts = []
    for e in effects:
        target = "Enemy" if e.is_hostile else "Player"

        if e.duration > 0:
            # Hostile timed effects in weapon enchantments are per-second DoTs/debuffs.
            if e.is_hostile:
                effect_str = f"[{e.magnitude:+g} {e.actor_value_name}/s*{e.duration}s]{{{target}}}"
            else:
                # Consumable/apparel timed effects are temporary modifiers, not per-second rates.
                effect_str = f"[{e.magnitude:+g} {e.actor_value_name}*{e.duration}s]{{{target}}}"
        else:
            # Instant/permanent: no duration suffix
            effect_str = f"[{e.magnitude:+g} {e.actor_value_name}]{{{target}}}"

        parts.append(effect_str)

    return ", ".join(parts)


def _effect_to_dict(e) -> dict:
    return {
        "actor_value_name": e.actor_value_name,
        "magnitude": e.magnitude,
        "duration": e.duration,
        "is_hostile": e.is_hostile,
        "is_conditional": getattr(e, "is_conditional", False),
    }


_WEAPON_VARIANT_TOKENS = (
    "npc",
    "boone",
    "veronica",
    "raul",
    "cass",
    "arcade",
    "lily",
    "companion",
    "eyebot",
    "chaineffect",
    "1hp",
    "upgrade",
)

_WEAPON_NON_PLAYER_TOKENS = (
    "securitron",
    "turret",
    "vertibird",
    "sentrybot",
    "misterhandy",
    "mistergutsy",
    "robobrain",
    "protectron",
    "eyebot",
    "satcom",
    "gojira",
    "queenant",
    "behemoth",
    "stranger",
    "rorschach",
    "gastrap",
    "spitmissile",
    "lakelurk",
    "sporeplant",
    "bloatfly",
    "firegecko",
    "fireant",
    "rexbite",
    "archimedesi",
    "dlc05alien",
    "1hp",
    "2hl",
    "2hr",
    "2hh",
)


def _looks_like_weapon_variant(editor_id: str) -> bool:
    lowered = editor_id.lower()
    return any(token in lowered for token in _WEAPON_VARIANT_TOKENS)


_WEAPON_VARIANT_LABELS = (
    ("lily", "Lily"),
    ("boone", "Boone"),
    ("veronica", "Veronica"),
    ("raul", "Raul"),
    ("cass", "Cass"),
    ("arcade", "Arcade"),
    ("companion", "Companion"),
    ("npc", "NPC"),
    ("upgrade", "Upgraded"),
    ("alwayscrit", "Always-Crit"),
    ("weak", "Weak"),
    ("broken", "Broken"),
    ("debug", "Debug"),
    ("missing", "Missing"),
    ("test", "Test"),
)


def _weapon_variant_label(editor_id: str) -> str | None:
    lowered = editor_id.lower()
    labels = [label for token, label in _WEAPON_VARIANT_LABELS if token in lowered]
    if not labels:
        return None
    unique_labels = []
    for label in labels:
        if label not in unique_labels:
            unique_labels.append(label)
    return ", ".join(unique_labels)


def _build_weapon_disambiguation_labels(weapons) -> dict[int, str]:
    """Return per-weapon labels for duplicated names.

    For names that appear multiple times, prefer human labels (Lily, Weak, etc.).
    If labels collide or are missing, fall back to editor IDs so each row is unique.
    """
    by_name: dict[str, list] = {}
    for w in weapons:
        by_name.setdefault(w.name, []).append(w)

    labels: dict[int, str] = {}
    for name, entries in by_name.items():
        if len(entries) < 2:
            continue

        proposed = {}
        for w in entries:
            proposed[w.form_id] = _weapon_variant_label(w.editor_id)

        # Count non-empty proposed labels to detect collisions.
        counts = Counter(label for label in proposed.values() if label)
        for w in entries:
            label = proposed[w.form_id]
            if not label or counts.get(label, 0) > 1:
                label = w.editor_id
            labels[w.form_id] = label

    return labels


def _looks_like_non_player_weapon(editor_id: str) -> bool:
    lowered = editor_id.lower()
    if lowered.startswith(("ms04", "trap")):
        return True
    return any(token in lowered for token in _WEAPON_NON_PLAYER_TOKENS)


def _is_player_facing_weapon(w) -> bool:
    # Prefer parsed WEAP DNAM flags when available.
    if getattr(w, "is_non_playable_flagged", False):
        return False
    if getattr(w, "is_embedded_weapon", False):
        return False
    eid = w.editor_id.lower()
    if _looks_like_weapon_variant(eid) or _looks_like_non_player_weapon(eid):
        return False
    # In FalloutNV.esm, player-facing weapons are consistently EDIDs containing
    # "weap". Header non-playable flags are not reliable for WEAP records.
    return "weap" in eid or eid == "fists"


def _weapon_classification(w) -> dict[str, bool]:
    return {
        "record_flag_playable": bool(w.is_playable),
        "non_playable_flagged": bool(getattr(w, "is_non_playable_flagged", False)),
        "embedded_weapon_flagged": bool(getattr(w, "is_embedded_weapon", False)),
        "is_variant": _looks_like_weapon_variant(w.editor_id),
        "is_non_player": _looks_like_non_player_weapon(w.editor_id),
        "is_player_facing": _is_player_facing_weapon(w),
    }


def _weapon_dump_key(w) -> tuple:
    effect_key = tuple(
        (e.actor_value_name, round(e.magnitude, 4), round(e.duration, 4), bool(e.is_hostile))
        for e in w.stat_effects
    )
    return (
        w.name,
        w.damage,
        w.value,
        w.weight,
        effect_key,
    )


def _weapon_display_score(w) -> tuple[int, int, int]:
    """Lower score = better representative for display/dedup."""
    eid = w.editor_id.lower()
    variant_penalty = int(_looks_like_weapon_variant(w.editor_id))
    # Prefer shorter, cleaner EDIDs when collapsing variants.
    return (variant_penalty, len(eid), eid.count("_"))


def _dedupe_weapons_for_display(weapons):
    grouped: dict[tuple, list] = {}
    for w in weapons:
        grouped.setdefault(_weapon_dump_key(w), []).append(w)
    deduped = []
    for key in grouped:
        candidates = grouped[key]
        candidates.sort(key=_weapon_display_score)
        deduped.append(candidates[0])
    return deduped


def _weapon_display_name(w, disambiguation_labels: dict[int, str]) -> str:
    display_name = w.name
    disambiguation_label = disambiguation_labels.get(w.form_id)
    if disambiguation_label:
        return f"{display_name} [{disambiguation_label}]"
    variant_label = _weapon_variant_label(w.editor_id)
    if variant_label:
        return f"{display_name} [{variant_label} variant]"
    return display_name


def _warn_if_missing_all_groups(plugin_datas: list[bytes], parser_fn, label: str) -> None:
    for data in plugin_datas:
        try:
            parser_fn(data)
            return
        except Exception as exc:
            if is_missing_grup_error(exc):
                continue
            raise
    print(f"Warning: GRUP for {label} not found in provided plugins; skipping.")


def main():
    parser = argparse.ArgumentParser(description="Dump FNV items from ESM")
    parser.add_argument("--esm", type=Path, action="append",
                        help="Plugin path; repeat in load order (last wins).")
    parser.add_argument("--armor", action="store_true", help="Show armor")
    parser.add_argument("--weapons", action="store_true", help="Show weapons")
    parser.add_argument("--consumables", action="store_true", help="Show consumables")
    parser.add_argument("--books", action="store_true", help="Show books")
    parser.add_argument("--playable-only", action="store_true",
                        help="Only show playable items (armor/weapons)")
    parser.add_argument("--verbose", action="store_true",
                        help="Show form IDs and editor IDs")
    parser.add_argument("--exclude-variants", action="store_true",
                        help="Hide obvious NPC/companion/helper weapon variants")
    parser.add_argument("--dedupe", action="store_true",
                        help="Collapse duplicate weapon rows by displayed stats")
    parser.add_argument("--include-companion-variants", action="store_true",
                        help="Include companion/NPC weapon variants in --playable-only output")
    parser.add_argument("--format", choices=("text", "json"), default="text",
                        help="Output format (default: text)")
    args = parser.parse_args()

    try:
        esm_paths, missing, _is_explicit = resolve_plugins_for_cli(args.esm, DEFAULT_ESM)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        raise SystemExit(1)

    if missing:
        print("Warning: some default vanilla plugins are missing and will be skipped:")
        for p in missing:
            print(f"  - {p.name}")

    # If no category selected, show all
    show_all = not (args.armor or args.weapons or args.consumables or args.books)

    plugin_datas = load_plugin_bytes(esm_paths)
    gmst = GameSettings.from_plugins(plugin_datas)
    book_points = gmst.skill_book_base_points()
    resolver = EffectResolver.from_plugins(plugin_datas)
    output: dict[str, object] = {
        "esm_paths": [str(p) for p in esm_paths],
        "categories": {},
    }

    if show_all or args.armor:
        armors = parse_records_merged(plugin_datas, parse_all_armors, missing_group_ok=True)
        if not armors:
            _warn_if_missing_all_groups(plugin_datas, parse_all_armors, "armor")
        if args.playable_only:
            armors = [a for a in armors if a.is_playable]
        for a in armors:
            resolver.resolve_armor(a)
        armors.sort(key=lambda a: a.name)
        if args.format == "json":
            output["categories"]["armor"] = {
                "total": len(armors),
                "items": [
                    {
                        "form_id": a.form_id,
                        "editor_id": a.editor_id,
                        "name": a.name,
                        "damage_threshold": a.damage_threshold,
                        "value": a.value,
                        "weight": a.weight,
                        "is_playable": a.is_playable,
                        "effects": [_effect_to_dict(e) for e in a.stat_effects],
                    }
                    for a in armors
                ],
            }
        else:
            print("=== ARMOR ===")
            for a in armors:
                effects = format_effects(a.stat_effects)
                print(f"{a.name} | DT: {a.damage_threshold:g} | Value: {a.value} | Weight: {a.weight:g}")
                if effects:
                    print(f"  {effects}")
            print(f"Total: {len(armors)} armor\n")

    if show_all or args.weapons:
        weapons = parse_records_merged(plugin_datas, parse_all_weapons, missing_group_ok=True)
        if not weapons:
            _warn_if_missing_all_groups(plugin_datas, parse_all_weapons, "weapons")
        for w in weapons:
            resolver.resolve_weapon(w)
        if args.playable_only:
            if args.include_companion_variants:
                weapons = [w for w in weapons if not _looks_like_non_player_weapon(w.editor_id)]
            else:
                weapons = [w for w in weapons if _is_player_facing_weapon(w)]
        if args.exclude_variants:
            weapons = [w for w in weapons if not _looks_like_weapon_variant(w.editor_id)]
        if args.dedupe:
            weapons = _dedupe_weapons_for_display(weapons)
        weapons.sort(key=lambda w: w.name)
        disambiguation_labels = _build_weapon_disambiguation_labels(weapons)
        if args.format == "json":
            output["categories"]["weapons"] = {
                "total": len(weapons),
                "items": [
                    {
                        "form_id": w.form_id,
                        "editor_id": w.editor_id,
                        "name": w.name,
                        "display_name": _weapon_display_name(w, disambiguation_labels),
                        "damage": w.damage,
                        "value": w.value,
                        "weight": w.weight,
                        "weapon_flags_1": int(getattr(w, "weapon_flags_1", 0)),
                        "weapon_flags_2": int(getattr(w, "weapon_flags_2", 0)),
                        **_weapon_classification(w),
                        "effects": [_effect_to_dict(e) for e in w.stat_effects],
                    }
                    for w in weapons
                ],
            }
        else:
            print("=== WEAPONS ===")
            for w in weapons:
                effects = format_effects(w.stat_effects)
                display_name = _weapon_display_name(w, disambiguation_labels)
                print(f"{display_name} | Dmg: {w.damage} | Value: {w.value} | Weight: {w.weight:g}")
                if args.verbose:
                    print(f"  form_id={w.form_id:#010x} editor_id={w.editor_id}")
                if effects:
                    print(f"  {effects}")
            print(f"Total: {len(weapons)} weapons\n")

    if show_all or args.consumables:
        consumables = parse_records_merged(plugin_datas, parse_all_consumables, missing_group_ok=True)
        if not consumables:
            _warn_if_missing_all_groups(plugin_datas, parse_all_consumables, "consumables")
        for c in consumables:
            resolver.resolve_consumable(c)
        consumables.sort(key=lambda c: c.name)
        if args.format == "json":
            output["categories"]["consumables"] = {
                "total": len(consumables),
                "items": [
                    {
                        "form_id": c.form_id,
                        "editor_id": c.editor_id,
                        "name": c.name,
                        "value": c.value,
                        "weight": c.weight,
                        "is_food": c.is_food,
                        "is_medicine": c.is_medicine,
                        "effects": [_effect_to_dict(e) for e in c.stat_effects],
                    }
                    for c in consumables
                ],
            }
        else:
            print("=== CONSUMABLES ===")
            for c in consumables:
                effects = format_effects(c.stat_effects)
                tag = ""
                if c.is_medicine:
                    tag = " [Medicine]"
                elif c.is_food:
                    tag = " [Food]"
                print(f"{c.name}{tag} | Value: {c.value} | Weight: {c.weight:g}")
                if effects:
                    print(f"  {effects}")
            print(f"Total: {len(consumables)} consumables\n")

    if show_all or args.books:
        books = parse_records_merged(plugin_datas, parse_all_books, missing_group_ok=True)
        if not books:
            _warn_if_missing_all_groups(plugin_datas, parse_all_books, "books")
        skill_books = [b for b in books if b.is_skill_book]
        skill_books.sort(key=lambda b: b.name)
        if args.format == "json":
            output["categories"]["books"] = {
                "total_books": len(books),
                "total_skill_books": len(skill_books),
                "items": [
                    {
                        "form_id": b.form_id,
                        "editor_id": b.editor_id,
                        "name": b.name,
                        "skill_name": b.skill_name,
                        "skill_points_per_book": book_points,
                        "value": b.value,
                    }
                    for b in skill_books
                ],
            }
        else:
            print("=== SKILL BOOKS ===")
            for b in skill_books:
                print(f"{b.name} | {b.skill_name} (+{book_points}) | Value: {b.value}")
            print(f"Total: {len(skill_books)} skill books (of {len(books)} books)\n")

    if args.format == "json":
        print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
