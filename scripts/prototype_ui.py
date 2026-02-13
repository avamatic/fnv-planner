"""Interactive CLI prototype for Build / Progression / Library flows.

Usage:
    python -m scripts.prototype_ui [--esm PATH]
"""

from __future__ import annotations

import argparse
import shlex
from pathlib import Path

from fnv_planner.engine.build_engine import BuildEngine
from fnv_planner.engine.ui_model import BuildUiModel
from fnv_planner.graph.dependency_graph import DependencyGraph
from fnv_planner.models.constants import ACTOR_VALUE_NAMES, SPECIAL_INDICES, ActorValue
from fnv_planner.models.game_settings import GameSettings
from fnv_planner.models.item import Armor, Weapon
from fnv_planner.models.perk import Perk
from fnv_planner.parser.effect_resolver import EffectResolver
from fnv_planner.parser.item_parser import parse_all_armors, parse_all_weapons
from fnv_planner.parser.perk_parser import parse_all_perks
from fnv_planner.parser.plugin_merge import (
    effective_vanilla_level_cap,
    has_non_base_level_cap_override,
    load_plugin_bytes,
    parse_records_merged,
    resolve_plugins_for_cli,
)


DEFAULT_ESM = Path(
    "/home/am/.local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm"
)

AV = ActorValue
NAME_TO_AV = {name.lower(): av for av, name in ACTOR_VALUE_NAMES.items()}


def _balanced_special() -> dict[int, int]:
    return {
        AV.STRENGTH: 5,
        AV.PERCEPTION: 5,
        AV.ENDURANCE: 5,
        AV.CHARISMA: 5,
        AV.INTELLIGENCE: 10,
        AV.AGILITY: 5,
        AV.LUCK: 5,
    }


def _parse_perk_id(text: str) -> int:
    return int(text, 0)


def _parse_actor_value(text: str) -> int:
    text = text.strip()
    if text.isdigit():
        return int(text)
    lowered = text.lower().replace("_", " ")
    if lowered in NAME_TO_AV:
        return int(NAME_TO_AV[lowered])
    raise ValueError(f"Unknown actor value: {text}")


def _parse_skill_points(parts: list[str]) -> dict[int, int]:
    points: dict[int, int] = {}
    for token in parts:
        if "=" not in token:
            raise ValueError(f"Invalid allocation token: {token}")
        key, raw = token.split("=", 1)
        av = _parse_actor_value(key)
        points[av] = int(raw, 10)
    return points


class PrototypeCli:
    def __init__(
        self,
        engine: BuildEngine,
        ui_model: BuildUiModel,
        perks: dict[int, Perk],
        armors: dict[int, Armor],
        weapons: dict[int, Weapon],
    ) -> None:
        self.engine = engine
        self.ui = ui_model
        self.perks = perks
        self.armors = armors
        self.weapons = weapons
        self.current_level = 1

    def run(self) -> None:
        print("FNV Planner Prototype CLI")
        print("Type 'help' for commands.")
        while True:
            try:
                raw = input("planner> ").strip()
            except (KeyboardInterrupt, EOFError):
                print()
                return
            if not raw:
                continue
            try:
                if self._dispatch(raw):
                    return
            except Exception as exc:
                print(f"error: {exc}")

    def _dispatch(self, raw: str) -> bool:
        args = shlex.split(raw)
        cmd = args[0].lower()
        rest = args[1:]

        if cmd in {"quit", "exit"}:
            return True
        if cmd == "help":
            self._help()
            return False
        if cmd == "build":
            self._print_build()
            return False
        if cmd == "progress":
            self._print_progress(rest)
            return False
        if cmd == "library":
            self._print_library(rest)
            return False
        if cmd == "target":
            self.engine.set_target_level(int(rest[0], 10))
            if self.current_level > self.engine.state.target_level:
                self.current_level = self.engine.state.target_level
            self._print_build()
            return False
        if cmd == "level":
            level = int(rest[0], 10)
            if level < 1 or level > self.engine.max_level:
                raise ValueError(f"level out of range (1..{self.engine.max_level})")
            if level > self.engine.state.target_level:
                self.engine.set_target_level(level)
            self.current_level = level
            self._print_build()
            return False
        if cmd == "remove":
            idx = int(rest[0], 10)
            entities = self.ui.selected_entities()
            if idx < 1 or idx > len(entities):
                raise ValueError("index out of range")
            if not self.ui.remove_selected_entity(entities[idx - 1]):
                raise ValueError("entity could not be removed")
            self._print_build()
            return False
        if cmd == "compare":
            from_level = int(rest[0], 10)
            to_level = int(rest[1], 10)
            self._print_compare(from_level, to_level)
            return False
        if cmd == "perk":
            self._perk_cmd(rest)
            self._print_build()
            return False
        if cmd == "trait":
            self.engine.toggle_trait(_parse_perk_id(rest[1])) if rest[0] == "toggle" else None
            self._print_build()
            return False
        if cmd == "tag":
            if rest[0] != "toggle":
                raise ValueError("usage: tag toggle <skill>")
            av = _parse_actor_value(rest[1])
            if not self.engine.toggle_tagged_skill(av):
                raise ValueError("tag toggle rejected")
            self._print_build()
            return False
        if cmd == "special":
            if rest[0] != "set":
                raise ValueError("usage: special set <stat> <value>")
            av = _parse_actor_value(rest[1])
            value = int(rest[2], 10)
            state = self.engine.state
            special = dict(state.special)
            special[av] = value
            self.engine.set_special_working(special)
            self._print_build()
            return False
        if cmd == "skills":
            self._skills_cmd(rest)
            self._print_build()
            return False
        if cmd == "equip":
            self._equip_cmd(rest)
            self._print_build()
            return False

        raise ValueError(f"unknown command: {cmd}")

    def _perk_cmd(self, rest: list[str]) -> None:
        sub = rest[0]
        if sub == "set":
            level = int(rest[1], 10)
            perk_id = _parse_perk_id(rest[2])
            self.engine.select_perk(level, perk_id)
            return
        if sub == "clear":
            level = int(rest[1], 10)
            self.engine.remove_perk(level)
            return
        if sub == "available":
            level = int(rest[1], 10) if len(rest) > 1 else self.current_level
            available = self.engine.available_perks_at(level)
            print(f"available perks at L{level}:")
            for pid in available[:50]:
                name = self.perks.get(pid).name if pid in self.perks else f"{pid:#x}"
                print(f"  {pid:#x}  {name}")
            if len(available) > 50:
                print(f"  ... and {len(available) - 50} more")
            return
        raise ValueError("usage: perk set|clear|available ...")

    def _skills_cmd(self, rest: list[str]) -> None:
        if rest[0] != "set":
            raise ValueError("usage: skills set <level> <skill=points>...")
        level = int(rest[1], 10)
        points = _parse_skill_points(rest[2:])
        self.engine.allocate_skill_points(level, points)

    def _equip_cmd(self, rest: list[str]) -> None:
        sub = rest[0]
        if sub == "set":
            slot = int(rest[1], 10)
            form_id = int(rest[2], 0)
            self.engine.set_equipment(slot, form_id)
            return
        if sub == "clear":
            slot = int(rest[1], 10)
            self.engine.clear_equipment_slot(slot)
            return
        raise ValueError("usage: equip set|clear ...")

    def _help(self) -> None:
        print(
            "\nCommands:\n"
            "  build                              Show current build summary\n"
            "  progress [from] [to]               Show progression snapshots\n"
            "  compare <from> <to>                Show stat/skill deltas\n"
            "  library [query]                    Browse gear library\n"
            "  target <level>                     Set target level\n"
            "  level <level>                      Set current preview level\n"
            "  remove <index>                     Remove entity from selected list\n"
            "  special set <stat> <value>         Set SPECIAL stat (supports names)\n"
            "  tag toggle <skill>                 Toggle tag skill\n"
            "  trait toggle <perk_id>             Toggle trait by form id (hex ok)\n"
            "  perk set <level> <perk_id>         Select perk at level\n"
            "  perk clear <level>                 Clear perk at level\n"
            "  perk available [level]             List available perks\n"
            "  skills set <level> k=v k=v ...     Set level skill allocation\n"
            "  equip set <slot> <form_id>         Equip item id in slot\n"
            "  equip clear <slot>                 Clear slot\n"
            "  quit                               Exit\n"
        )

    def _print_build(self) -> None:
        state = self.engine.state
        print(
            f"\nBUILD  current=L{self.current_level}  target=L{state.target_level}  max=L{self.engine.max_level}  "
            f"valid={'yes' if self.engine.is_valid() else 'no'}"
        )
        snap = self.ui.level_snapshot(self.current_level)
        target_snap = self.ui.level_snapshot(state.target_level)
        delta = self.ui.compare_levels(self.current_level, state.target_level)
        print(
            f"Now: HP {snap.stats.hit_points} AP {snap.stats.action_points} "
            f"CW {snap.stats.carry_weight:.0f} Crit {snap.stats.crit_chance:.0f}"
        )
        print(
            f"Target: HP {target_snap.stats.hit_points} AP {target_snap.stats.action_points} "
            f"CW {target_snap.stats.carry_weight:.0f} Crit {target_snap.stats.crit_chance:.0f}"
        )
        print(
            f"Delta: HP {delta.stat_deltas['hit_points']:+.0f} "
            f"AP {delta.stat_deltas['action_points']:+.0f} "
            f"CW {delta.stat_deltas['carry_weight']:+.0f} "
            f"Crit {delta.stat_deltas['crit_chance']:+.0f}"
        )

        entities = self.ui.selected_entities()
        print("Selected entities:")
        for i, entity in enumerate(entities, start=1):
            print(f"  {i:>2}. [{entity.kind}] {entity.label}")
        if not entities:
            print("  (none)")

    def _print_progress(self, rest: list[str]) -> None:
        if rest:
            from_level = int(rest[0], 10)
            to_level = int(rest[1], 10) if len(rest) > 1 else self.engine.state.target_level
        else:
            from_level = 1
            to_level = self.engine.state.target_level
        snaps = self.ui.progression(from_level, to_level)
        print(f"\nPROGRESSION L{from_level}..L{to_level}")
        for snap in snaps:
            perk = f"{snap.perk_id:#x}" if snap.perk_id is not None else "-"
            print(
                f"  L{snap.level:>2}: perk={perk:<10} "
                f"spent={snap.spent_skill_points:>2} unspent={snap.unspent_skill_points:>2} "
                f"HP={snap.stats.hit_points:>3} AP={snap.stats.action_points:>2} "
                f"Guns={snap.stats.skills.get(AV.GUNS, 0):>3}"
            )

    def _print_compare(self, from_level: int, to_level: int) -> None:
        cmp = self.ui.compare_levels(from_level, to_level)
        print(f"\nCOMPARE L{from_level} -> L{to_level}")
        for key, value in cmp.stat_deltas.items():
            if value:
                print(f"  {key:<22} {value:+.2f}")
        if cmp.skill_deltas:
            print("  skill deltas:")
            for av, value in sorted(cmp.skill_deltas.items()):
                print(f"    {ACTOR_VALUE_NAMES.get(av, f'AV{av}'):<16} {value:+d}")

    def _print_library(self, rest: list[str]) -> None:
        query = " ".join(rest).strip()
        items = self.ui.gear_catalog(query=query)
        print(f"\nLIBRARY query={query!r} count={len(items)}")
        for item in items[:200]:
            print(
                f"  {item.kind:<6} {item.form_id:#010x} "
                f"slot={item.slot:<2} value={item.value:<5} wt={item.weight:<5.1f} {item.name}"
            )
        if len(items) > 200:
            print(f"  ... and {len(items) - 200} more")


def _build_engine_from_data(
    plugin_datas: list[bytes] | None,
    plugin_paths: list[Path] | None = None,
) -> tuple[BuildEngine, dict[int, Perk], dict[int, Armor], dict[int, Weapon]]:
    if not plugin_datas:
        gmst = GameSettings.defaults()
        perks: list[Perk] = []
        armors: dict[int, Armor] = {}
        weapons: dict[int, Weapon] = {}
    else:
        gmst = GameSettings.from_plugins(plugin_datas)
        if not gmst._values:
            print("Warning: GMST GRUP not found in provided plugins; using vanilla defaults.")
            gmst = GameSettings.defaults()
        elif plugin_paths:
            has_override = has_non_base_level_cap_override(plugin_paths, plugin_datas)
            gmst._values["iMaxCharacterLevel"] = effective_vanilla_level_cap(
                plugin_paths,
                gmst.get_int("iMaxCharacterLevel", 50),
                has_non_base_cap_override=has_override,
            )
        perks = parse_records_merged(plugin_datas, parse_all_perks, missing_group_ok=True)
        graph = DependencyGraph.build(perks)
        engine = BuildEngine.new_build(gmst, graph)

        resolver = EffectResolver.from_plugins(plugin_datas)
        armors_list = parse_records_merged(plugin_datas, parse_all_armors, missing_group_ok=True)
        weapons_list = parse_records_merged(plugin_datas, parse_all_weapons, missing_group_ok=True)
        for armor in armors_list:
            resolver.resolve_armor(armor)
        for weapon in weapons_list:
            resolver.resolve_weapon(weapon)
        armors = {a.form_id: a for a in armors_list if a.is_playable}
        weapons = {w.form_id: w for w in weapons_list if w.is_playable}
        perk_map = {p.form_id: p for p in perks}
        _init_default_build(engine)
        return engine, perk_map, armors, weapons

    graph = DependencyGraph.build(perks)
    engine = BuildEngine.new_build(gmst, graph)
    perk_map = {p.form_id: p for p in perks}
    _init_default_build(engine)
    return engine, perk_map, armors, weapons


def _init_default_build(engine: BuildEngine) -> None:
    engine.set_special(_balanced_special())
    engine.set_sex(0)
    engine.set_tagged_skills({AV.GUNS, AV.LOCKPICK, AV.SPEECH})
    engine.set_target_level(engine.max_level)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run interactive FNV planner prototype CLI")
    parser.add_argument(
        "--esm",
        type=Path,
        action="append",
        help="Plugin path; repeat in load order (last wins).",
    )
    args = parser.parse_args()

    plugin_datas: list[bytes] | None = None
    try:
        esm_paths, missing, _is_explicit = resolve_plugins_for_cli(args.esm, DEFAULT_ESM)
    except FileNotFoundError as exc:
        print(f"Warning: {exc}")
        print("No plugins found; running in defaults-only mode.")
        esm_paths = []
        missing = []

    if missing:
        print("Warning: some default vanilla plugins are missing and will be skipped:")
        for p in missing:
            print(f"  - {p.name}")
    if esm_paths:
        print(f"Loading plugins: {', '.join(str(p) for p in esm_paths)}")
        plugin_datas = load_plugin_bytes(esm_paths)

    engine, perks, armors, weapons = _build_engine_from_data(plugin_datas, esm_paths)
    print(f"Max character level from game data: {engine.max_level}")
    ui = BuildUiModel(engine, armors=armors, weapons=weapons)
    cli = PrototypeCli(engine, ui, perks, armors, weapons)
    cli.run()


if __name__ == "__main__":
    main()
