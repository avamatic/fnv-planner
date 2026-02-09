"""Dump items from FalloutNV.esm with resolved stat effects.

Usage:
    python -m scripts.dump_items [--esm PATH] [--armor] [--weapons]
                                 [--consumables] [--books] [--playable-only]

If no category flags are given, all categories are shown.
"""

import argparse
from pathlib import Path

from fnv_planner.parser.effect_resolver import EffectResolver
from fnv_planner.parser.item_parser import (
    parse_all_armors,
    parse_all_books,
    parse_all_consumables,
    parse_all_weapons,
)


DEFAULT_ESM = Path(
    "/home/am/.local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm"
)


def format_effects(effects) -> str:
    """Format stat effects with duration and context (enemy vs player).

    Format: [(effect/s)*(effect_time*s)]{Enemy/Player}
    - DoT: [-2 Health/s*10s]{Enemy}
    - Instant: [-50 Health]{Enemy}
    - Permanent buff: [+1 Luck]{Player}
    - Temporary buff: [+5 Health/s*6s]{Player}
    """
    if not effects:
        return ""

    parts = []
    for e in effects:
        target = "Enemy" if e.is_hostile else "Player"

        if e.duration > 0:
            # Over time: show rate per second and duration
            effect_str = f"[{e.magnitude:+g} {e.actor_value_name}/s*{e.duration}s]{{{target}}}"
        else:
            # Instant/permanent: no duration suffix
            effect_str = f"[{e.magnitude:+g} {e.actor_value_name}]{{{target}}}"

        parts.append(effect_str)

    return ", ".join(parts)


def main():
    parser = argparse.ArgumentParser(description="Dump FNV items from ESM")
    parser.add_argument("--esm", type=Path, default=DEFAULT_ESM,
                        help="Path to FalloutNV.esm")
    parser.add_argument("--armor", action="store_true", help="Show armor")
    parser.add_argument("--weapons", action="store_true", help="Show weapons")
    parser.add_argument("--consumables", action="store_true", help="Show consumables")
    parser.add_argument("--books", action="store_true", help="Show books")
    parser.add_argument("--playable-only", action="store_true",
                        help="Only show playable items (armor/weapons)")
    args = parser.parse_args()

    if not args.esm.exists():
        print(f"Error: ESM not found at {args.esm}")
        raise SystemExit(1)

    # If no category selected, show all
    show_all = not (args.armor or args.weapons or args.consumables or args.books)

    data = args.esm.read_bytes()
    resolver = EffectResolver.from_esm(data)

    if show_all or args.armor:
        armors = parse_all_armors(data)
        if args.playable_only:
            armors = [a for a in armors if a.is_playable]
        for a in armors:
            resolver.resolve_armor(a)
        armors.sort(key=lambda a: a.name)

        print("=== ARMOR ===")
        for a in armors:
            effects = format_effects(a.stat_effects)
            print(f"{a.name} | DT: {a.damage_threshold:g} | Value: {a.value} | Weight: {a.weight:g}")
            if effects:
                print(f"  {effects}")
        print(f"Total: {len(armors)} armor\n")

    if show_all or args.weapons:
        weapons = parse_all_weapons(data)
        if args.playable_only:
            weapons = [w for w in weapons if w.is_playable]
        for w in weapons:
            resolver.resolve_weapon(w)
        weapons.sort(key=lambda w: w.name)

        print("=== WEAPONS ===")
        for w in weapons:
            effects = format_effects(w.stat_effects)
            print(f"{w.name} | Dmg: {w.damage} | Value: {w.value} | Weight: {w.weight:g}")
            if effects:
                print(f"  {effects}")
        print(f"Total: {len(weapons)} weapons\n")

    if show_all or args.consumables:
        consumables = parse_all_consumables(data)
        for c in consumables:
            resolver.resolve_consumable(c)
        consumables.sort(key=lambda c: c.name)

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
        books = parse_all_books(data)
        skill_books = [b for b in books if b.is_skill_book]
        skill_books.sort(key=lambda b: b.name)

        print("=== SKILL BOOKS ===")
        for b in skill_books:
            print(f"{b.name} | {b.skill_name} (+1) | Value: {b.value}")
        print(f"Total: {len(skill_books)} skill books (of {len(books)} books)\n")


if __name__ == "__main__":
    main()
