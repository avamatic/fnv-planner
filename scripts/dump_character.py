"""Dump computed stats for a sample character build.

Creates a sample build and computes all derived stats to verify the
full pipeline: SPECIAL → skills → equipment → derived stats.

Usage:
    python -m scripts.dump_character [--esm PATH]

Without --esm, uses vanilla defaults for GMST values and no equipment.
With --esm, loads GMST from the ESM and can resolve equipment effects.
"""

import argparse
from pathlib import Path

from fnv_planner.models.character import Character
from fnv_planner.models.constants import ACTOR_VALUE_NAMES, ActorValue
from fnv_planner.models.derived_stats import compute_stats
from fnv_planner.models.game_settings import GameSettings
from fnv_planner.parser.plugin_merge import (
    load_plugin_bytes,
    parse_records_merged,
    resolve_plugins_for_cli,
)


AV = ActorValue

DEFAULT_ESM = Path(
    "/home/am/.local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm"
)


def main():
    parser = argparse.ArgumentParser(description="Dump sample character stats")
    parser.add_argument("--esm", type=Path, action="append",
                        help="Plugin path; repeat in load order (last wins)")
    args = parser.parse_args()

    # Build a sample character
    courier = Character(
        name="The Courier",
        level=20,
    )
    courier.special = {
        AV.STRENGTH: 6,
        AV.PERCEPTION: 6,
        AV.ENDURANCE: 7,
        AV.CHARISMA: 3,
        AV.INTELLIGENCE: 8,
        AV.AGILITY: 6,
        AV.LUCK: 7,
    }
    courier.tagged_skills = {AV.GUNS, AV.LOCKPICK, AV.SCIENCE}
    courier.skill_points_spent = {
        AV.GUNS: 50,
        AV.LOCKPICK: 40,
        AV.SCIENCE: 45,
        AV.REPAIR: 30,
        AV.MEDICINE: 20,
        AV.SPEECH: 25,
        AV.SNEAK: 15,
    }

    # Load GMST + equipment if ESM available
    armors = {}
    weapons = {}
    fallback_announced = False
    try:
        existing, missing, _is_explicit = resolve_plugins_for_cli(args.esm, DEFAULT_ESM)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        print("No plugin found — using vanilla GMST defaults, no equipment")
        gmst = GameSettings.defaults()
        existing = []
        missing = []
        fallback_announced = True

    if existing:
        if missing:
            print("Warning: some default vanilla plugins are missing and will be skipped:")
            for p in missing:
                print(f"  - {p.name}")
        print(f"Loading plugins: {', '.join(str(p) for p in existing)}")
        plugin_datas = load_plugin_bytes(existing)
        gmst = GameSettings.from_plugins(plugin_datas)
        if not gmst._values:
            print("Warning: GMST GRUP not found; using vanilla defaults.")
            gmst = GameSettings.defaults()

        # Resolve equipment if ESM is present
        from fnv_planner.parser.effect_resolver import EffectResolver
        from fnv_planner.parser.item_parser import parse_all_armors, parse_all_weapons

        armor_list = []
        weapon_list = []
        try:
            resolver = EffectResolver.from_plugins(plugin_datas)
            armor_list = parse_records_merged(plugin_datas, parse_all_armors, missing_group_ok=True)
            weapon_list = parse_records_merged(plugin_datas, parse_all_weapons, missing_group_ok=True)
            for a in armor_list:
                resolver.resolve_armor(a)
            for w in weapon_list:
                resolver.resolve_weapon(w)
            armors = {a.form_id: a for a in armor_list}
            weapons = {w.form_id: w for w in weapon_list}
        except ValueError as exc:
            if "not found in plugin" in str(exc):
                print("Warning: required item/effect GRUP missing; continuing without equipment.")
                armors = {}
                weapons = {}
            else:
                raise

        # Equip Lucky Shades (+1 Luck, +3 Perception)
        if armor_list:
            armor_by_edid = {a.editor_id: a for a in armor_list}
            if "UniqueGlassesLuckyShades" in armor_by_edid:
                shades = armor_by_edid["UniqueGlassesLuckyShades"]
                courier.equipment[0] = shades.form_id
                print(f"Equipped: {shades.name} (form_id: {shades.form_id:#x})")
    else:
        if not fallback_announced:
            print("No plugin found — using vanilla GMST defaults, no equipment")
        if "gmst" not in locals():
            gmst = GameSettings.defaults()

    # Compute stats
    stats = compute_stats(courier, gmst, armors=armors, weapons=weapons)

    # Display
    print(f"\n{'='*50}")
    print(f"  {courier.name} — Level {courier.level}")
    print(f"{'='*50}")

    print("\n--- SPECIAL ---")
    for av in range(AV.STRENGTH, AV.LUCK + 1):
        base = courier.special[av]
        effective = stats.effective_special[av]
        name = ACTOR_VALUE_NAMES[av]
        bonus = effective - base
        bonus_str = f" (+{bonus})" if bonus > 0 else ""
        print(f"  {name:<14} {effective:>2}{bonus_str}")

    print("\n--- DERIVED STATS ---")
    print(f"  Hit Points          {stats.hit_points:>6}")
    print(f"  Action Points       {stats.action_points:>6}")
    print(f"  Carry Weight        {stats.carry_weight:>6.0f}")
    print(f"  Critical Chance     {stats.crit_chance:>5.0f}%")
    print(f"  Melee Damage Bonus  {stats.melee_damage:>6.1f}")
    print(f"  Unarmed Damage      {stats.unarmed_damage:>6.2f}")
    print(f"  Poison Resistance   {stats.poison_resistance:>5.0f}%")
    print(f"  Rad Resistance      {stats.rad_resistance:>5.0f}%")
    print(f"  Companion Nerve     {stats.companion_nerve:>5.0f}%")
    print(f"  Skill Pts/Level     {stats.skill_points_per_level:>6}")
    print(f"  Max Level           {stats.max_level:>6}")

    print("\n--- SKILLS ---")
    for skill_av in sorted(stats.skills.keys()):
        name = ACTOR_VALUE_NAMES.get(skill_av, f"AV{skill_av}")
        value = stats.skills[skill_av]
        tag = " [TAG]" if skill_av in courier.tagged_skills else ""
        print(f"  {name:<16} {value:>3}{tag}")

    if stats.equipment_bonuses:
        print("\n--- EQUIPMENT BONUSES ---")
        for av, mag in sorted(stats.equipment_bonuses.items()):
            name = ACTOR_VALUE_NAMES.get(av, f"AV{av}")
            print(f"  {name:<16} {mag:>+.0f}")

    print()


if __name__ == "__main__":
    main()
