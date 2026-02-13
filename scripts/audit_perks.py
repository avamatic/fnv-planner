"""Audit perk categories from one plugin stack.

Usage:
    python -m scripts.audit_perks [--esm PATH ...] [--show N] [--check-wiki]
"""

import argparse
from collections import Counter
from pathlib import Path

from fnv_planner.parser.perk_classification import (
    classify_perk,
    detect_challenge_perk_ids,
)
from fnv_planner.parser.perk_parser import parse_all_perks
from fnv_planner.parser.plugin_merge import (
    load_plugin_bytes,
    parse_records_merged,
    resolve_plugins_for_cli,
)


DEFAULT_ESM = Path(
    "/home/am/.local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm"
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit perk categories from plugin stack")
    parser.add_argument("--esm", type=Path, action="append",
                        help="Plugin path; repeat in load order (last wins)")
    parser.add_argument("--show", type=int, default=8,
                        help="Rows to show per category (default: 8)")
    parser.add_argument("--check-wiki", action="store_true",
                        help="Compare challenge/special counts with wiki expectations (16/18)")
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

    print(f"Loading plugins: {', '.join(str(p) for p in esm_paths)}")
    plugin_datas = load_plugin_bytes(esm_paths)
    perks = parse_records_merged(plugin_datas, parse_all_perks, missing_group_ok=True)
    challenge_ids = detect_challenge_perk_ids(plugin_datas, perks)

    by_category: dict[str, list] = {
        "normal": [],
        "trait": [],
        "challenge": [],
        "special": [],
        "internal": [],
    }
    for perk in perks:
        cat = classify_perk(perk, challenge_ids)
        by_category[cat.name].append(perk)

    counts = Counter({k: len(v) for k, v in by_category.items()})
    print("\n=== PERK CATEGORY COUNTS ===")
    print(f"Total: {len(perks)}")
    print(f"Normal:    {counts['normal']}")
    print(f"Trait:     {counts['trait']}")
    print(f"Challenge: {counts['challenge']}")
    print(f"Special:   {counts['special']}")
    print(f"Internal:  {counts['internal']}")

    if args.check_wiki:
        # https://fallout.fandom.com/wiki/Fallout:_New_Vegas_perks#Challenge_and_special_perks
        exp_challenge = 16
        print("\n=== WIKI CHECK ===")
        print(f"Challenge expected={exp_challenge}, actual={counts['challenge']}")
        print("Special expected=18 (curated wiki list), actual=data-driven visible non-selectable bucket")
        print(f"Special actual={counts['special']}")

    for category in ("challenge", "special", "trait", "internal", "normal"):
        rows = sorted(by_category[category], key=lambda p: p.name)
        print(f"\n=== {category.upper()} (showing up to {args.show}) ===")
        for perk in rows[:max(args.show, 0)]:
            print(f"{perk.name} | {perk.editor_id} | form_id=0x{perk.form_id:08X}")


if __name__ == "__main__":
    main()
