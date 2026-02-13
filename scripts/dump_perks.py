"""Dump all perks from FalloutNV.esm, sorted by level then name.

Usage:
    python -m scripts.dump_perks [--esm PATH] [--playable-only] [--traits-only]
"""

import argparse
from pathlib import Path

from fnv_planner.parser.perk_parser import parse_all_perks
from fnv_planner.parser.record_reader import read_grup
from fnv_planner.parser.plugin_merge import (
    load_plugin_bytes,
    parse_records_merged,
    resolve_plugins_for_cli,
)


DEFAULT_ESM = Path(
    "/home/am/.local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm"
)


def format_requirements(perk) -> str:
    """Format a perk's requirements as a compact string."""
    parts: list[str] = []

    if perk.sex_requirement:
        parts.append(perk.sex_requirement.name)

    for i, req in enumerate(perk.skill_requirements):
        prefix = "OR " if req.is_or else ""
        parts.append(f"{prefix}{req.name} {req.operator} {req.value}")

    for req in perk.level_requirements:
        parts.append(f"Level {req.operator} {req.value}")

    for req in perk.perk_requirements:
        parts.append(f"HasPerk(0x{req.perk_form_id:08X}) rank {req.rank}")

    for req in perk.raw_conditions:
        parts.append(f"Func{req.function}(p1={req.param1}) {req.operator} {req.value}")

    return ", ".join(parts) if parts else "None"


def _challenge_names_from_plugin(data: bytes) -> set[str]:
    try:
        records = read_grup(data, "CHAL")
    except ValueError as exc:
        if "GRUP 'CHAL' not found in plugin" in str(exc):
            return set()
        raise
    names: set[str] = set()
    for record in records:
        full_name = ""
        for sub in record.subrecords:
            if sub.type == "FULL":
                full_name = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
                break
        if full_name:
            names.add(full_name)
    return names


def _detect_challenge_perk_ids(plugin_datas: list[bytes], perks) -> set[int]:
    chal_names: set[str] = set()
    for data in plugin_datas:
        chal_names |= _challenge_names_from_plugin(data)

    ids: set[int] = set()
    for perk in perks:
        # Primary signal: PERK name is rewarded by a CHAL record.
        if perk.name in chal_names:
            ids.add(perk.form_id)
            continue
        # Secondary signal: challenge-family PERK editor IDs.
        # This captures challenge reward perks whose CHAL title differs.
        if "challenge" in perk.editor_id.lower():
            ids.add(perk.form_id)
    return ids


def main():
    parser = argparse.ArgumentParser(description="Dump FNV perks from ESM")
    parser.add_argument("--esm", type=Path, action="append",
                        help="Plugin path; repeat in load order (last wins).")
    parser.add_argument("--playable-only", action="store_true",
                        help="Only show playable perks")
    parser.add_argument("--traits-only", action="store_true",
                        help="Only show traits")
    parser.add_argument("--include-challenge-perks", action="store_true",
                        help="Include challenge reward perks in --playable-only output")
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

    plugin_datas = load_plugin_bytes(esm_paths)
    perks = parse_records_merged(plugin_datas, parse_all_perks, missing_group_ok=True)
    challenge_perk_ids = _detect_challenge_perk_ids(plugin_datas, perks)

    # Filter
    if args.playable_only:
        perks = [
            p for p in perks
            if p.is_playable
            and not p.is_trait
            and (args.include_challenge_perks or p.form_id not in challenge_perk_ids)
        ]
    elif args.traits_only:
        perks = [p for p in perks if p.is_trait]

    # Sort by level, then name
    perks.sort(key=lambda p: (p.min_level, p.name))

    # Print
    for p in perks:
        tag = "[Trait] " if p.is_trait else ""
        if p.form_id in challenge_perk_ids:
            tag = f"{tag}[Challenge] "
        playable = "" if p.is_playable else " (non-playable)"
        reqs = format_requirements(p)

        print(f"Level {p.min_level:>2} | {tag}{p.name}{playable}")
        print(f"         | Requires: {reqs}")
        if p.description:
            # Truncate long descriptions
            desc = p.description if len(p.description) <= 100 else p.description[:97] + "..."
            print(f"         | {desc}")
        print()

    print(f"Total: {len(perks)} perks")


if __name__ == "__main__":
    main()
