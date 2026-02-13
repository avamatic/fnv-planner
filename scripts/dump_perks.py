"""Dump all perks from FalloutNV.esm, sorted by level then name.

Usage:
    python -m scripts.dump_perks [--esm PATH] [--playable-only] [--traits-only]
"""

import argparse
from pathlib import Path

from fnv_planner.parser.perk_parser import parse_all_perks
from fnv_planner.parser.plugin_merge import (
    default_vanilla_plugins,
    load_plugin_bytes,
    parse_records_merged,
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


def main():
    parser = argparse.ArgumentParser(description="Dump FNV perks from ESM")
    parser.add_argument("--esm", type=Path, action="append",
                        help="Plugin path; repeat in load order (last wins).")
    parser.add_argument("--playable-only", action="store_true",
                        help="Only show playable perks")
    parser.add_argument("--traits-only", action="store_true",
                        help="Only show traits")
    args = parser.parse_args()

    if args.esm:
        esm_paths = args.esm
        missing = [p for p in esm_paths if not p.exists()]
        if missing:
            for p in missing:
                print(f"Error: ESM not found at {p}")
            raise SystemExit(1)
    else:
        esm_paths, missing = default_vanilla_plugins(DEFAULT_ESM)
        if missing:
            print("Warning: some default vanilla plugins are missing and will be skipped:")
            for p in missing:
                print(f"  - {p.name}")
        if not esm_paths:
            print("Error: no default plugins found. Pass --esm explicitly.")
            raise SystemExit(1)

    plugin_datas = load_plugin_bytes(esm_paths)
    perks = parse_records_merged(plugin_datas, parse_all_perks, missing_group_ok=True)

    # Filter
    if args.playable_only:
        perks = [p for p in perks if p.is_playable and not p.is_trait]
    elif args.traits_only:
        perks = [p for p in perks if p.is_trait]

    # Sort by level, then name
    perks.sort(key=lambda p: (p.min_level, p.name))

    # Print
    for p in perks:
        tag = "[Trait] " if p.is_trait else ""
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
