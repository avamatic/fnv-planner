"""Audit skill-book counts from plugin content.

Shows both raw per-plugin counts and merged (load-order) counts by skill.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from fnv_planner.models.constants import ACTOR_VALUE_NAMES
from fnv_planner.parser.book_stats import (
    placed_skill_book_copies_by_actor_value,
    skill_book_source_breakdown,
    skill_books_by_actor_value,
)
from fnv_planner.parser.item_parser import parse_all_books
from fnv_planner.parser.plugin_merge import (
    is_missing_grup_error,
    load_plugin_bytes,
    parse_records_merged,
    resolve_plugins_for_cli,
)

DEFAULT_ESM = Path(
    "/home/am/.local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm"
)


def _print_counts(prefix: str, counts: dict[int, int]) -> None:
    total = sum(counts.values())
    print(f"{prefix} total skill-book records: {total}")
    for av in sorted(counts):
        print(f"  - {ACTOR_VALUE_NAMES.get(av, f'AV{av}')}: {counts[av]}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit skill-book record counts")
    parser.add_argument("--esm", type=Path, action="append", help="Plugin path; repeat in load order")
    args = parser.parse_args()

    paths, missing, _is_explicit = resolve_plugins_for_cli(args.esm, DEFAULT_ESM)
    if missing:
        print("Warning: some default vanilla plugins are missing and will be skipped:")
        for p in missing:
            print(f"  - {p.name}")

    datas = load_plugin_bytes(paths)

    print("Per-plugin raw counts:")
    for path, data in zip(paths, datas):
        try:
            books = parse_all_books(data)
        except Exception as exc:
            if is_missing_grup_error(exc):
                print(f"{path.name} total skill-book records: 0")
                continue
            raise
        counts = skill_books_by_actor_value(books)
        _print_counts(f"{path.name}", counts)

    merged_books = parse_records_merged(datas, parse_all_books, missing_group_ok=True)
    merged_counts = skill_books_by_actor_value(merged_books)
    print("\nMerged load-order counts (last wins by form_id):")
    _print_counts("Merged", merged_counts)
    placed_counts = placed_skill_book_copies_by_actor_value(datas, merged_books)
    print("\nDetected copy counts (placed refs + inventory templates):")
    _print_counts("Placed", placed_counts)
    breakdown = skill_book_source_breakdown(datas, merged_books)
    print("\nSource buckets (for wiki-style comparison):")
    _print_counts("Static world", breakdown.static_world_by_av)
    _print_counts("Craftable (OWB recipe unlocks)", breakdown.craftable_by_av)
    _print_counts("Random pools (LVLI entries)", breakdown.random_pool_by_av)


if __name__ == "__main__":
    main()
