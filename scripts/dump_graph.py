"""Dump the perk dependency graph for a sample character build.

Builds the graph from FalloutNV.esm, shows available perks for a sample
character, and prints dependency chains for interesting perks.

Usage:
    python -m scripts.dump_graph [--esm PATH]
"""

import argparse
from pathlib import Path

from fnv_planner.graph.dependency_graph import DependencyGraph
from fnv_planner.models.character import Character
from fnv_planner.models.constants import ActorValue
from fnv_planner.models.derived_stats import compute_stats
from fnv_planner.models.game_settings import GameSettings
from fnv_planner.parser.perk_parser import parse_all_perks
from fnv_planner.parser.plugin_merge import (
    load_plugin_bytes,
    parse_records_merged,
    resolve_plugins_for_cli,
)


AV = ActorValue

DEFAULT_ESM = Path(
    "/home/am/.local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm"
)

# Perks with interesting dependency chains to display.
INTERESTING_PERKS = [
    "PiercingStrike",     # OR-group requirement
    "SlayerPerk",         # deep chain
    "GhastlyScavenger",   # raw conditions
    "LadyKiller",         # sex requirement
    "HereandNow",         # level < 30 cap
]


def main():
    parser = argparse.ArgumentParser(description="Dump perk dependency graph")
    parser.add_argument("--esm", type=Path, action="append",
                        help="Plugin path; repeat in load order (last wins).")
    args = parser.parse_args()

    try:
        esm_paths, missing, _is_explicit = resolve_plugins_for_cli(args.esm, DEFAULT_ESM)
    except FileNotFoundError as exc:
        print(f"Error: {exc}")
        return

    if missing:
        print("Warning: some default vanilla plugins are missing and will be skipped:")
        for p in missing:
            print(f"  - {p.name}")

    print(f"Loading plugins: {', '.join(str(p) for p in esm_paths)}")
    plugin_datas = load_plugin_bytes(esm_paths)
    gmst = GameSettings.from_plugins(plugin_datas)
    if not gmst._values:
        print("Warning: GMST GRUP not found in provided plugins; using vanilla defaults.")
        gmst = GameSettings.defaults()
    perks = parse_records_merged(plugin_datas, parse_all_perks, missing_group_ok=True)
    if not perks:
        print("Warning: PERK GRUP not found in provided plugins; graph will be empty.")

    graph = DependencyGraph.build(perks)

    perk_by_edid = {p.editor_id: p for p in perks}
    node_by_edid = {
        p.editor_id: graph.get_node(p.form_id)
        for p in perks
        if graph.get_node(p.form_id) is not None
    }

    # --- Graph overview ---
    playable_count = sum(
        1 for p in perks if p.is_playable and not p.is_trait
    )
    traits = graph.available_traits()
    topo = graph.topological_order()

    print(f"\n{'='*60}")
    print(f"  Dependency Graph Overview")
    print(f"{'='*60}")
    print(f"  Total perks:    {len(perks)}")
    print(f"  Playable perks: {playable_count}")
    print(f"  Traits:         {len(traits)}")
    print(f"  Topo order len: {len(topo)}")

    # --- Sample character ---
    courier = Character(
        name="The Courier",
        level=12,
        sex=0,  # Male
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
        AV.GUNS: 40,
        AV.LOCKPICK: 30,
        AV.SCIENCE: 35,
        AV.REPAIR: 20,
    }

    stats = compute_stats(courier, gmst)

    available = graph.available_perks(courier, stats)
    available_nodes = [graph.get_node(pid) for pid in available]
    available_nodes = [n for n in available_nodes if n is not None]
    available_nodes.sort(key=lambda n: n.name)

    print(f"\n{'='*60}")
    print(f"  Available Perks for {courier.name} (Level {courier.level})")
    print(f"{'='*60}")
    print(f"  {len(available)} perks available:\n")
    for node in available_nodes:
        print(f"    {node.name:<30} (min level {node.min_level})")

    # --- Interesting perk chains ---
    print(f"\n{'='*60}")
    print(f"  Dependency Chains & Requirements")
    print(f"{'='*60}")

    for edid in INTERESTING_PERKS:
        if edid not in perk_by_edid:
            continue
        perk = perk_by_edid[edid]
        node = graph.get_node(perk.form_id)
        if node is None:
            continue

        print(f"\n  {node.name} ({node.editor_id})")
        print(f"    Min level: {node.min_level}, Ranks: {node.ranks}")

        # Requirements
        if node.requirements.clauses:
            print(f"    Requirements:")
            for clause in node.requirements.clauses:
                if len(clause.requirements) == 1:
                    req = clause.requirements[0]
                    print(f"      - {_fmt_req(req)}")
                else:
                    parts = [_fmt_req(r) for r in clause.requirements]
                    print(f"      - One of: {' OR '.join(parts)}")
        if node.requirements.raw_conditions:
            print(f"    Raw conditions: {len(node.requirements.raw_conditions)}")

        # Dependency chain
        chain = graph.perk_chain(perk.form_id)
        if chain:
            chain_names = []
            for pid in chain:
                cn = graph.get_node(pid)
                chain_names.append(cn.name if cn else f"{pid:#x}")
            print(f"    Perk chain: {' → '.join(chain_names)} → {node.name}")

        # Unmet for sample character
        unmet = graph.unmet_requirements(perk.form_id, courier, stats)
        if unmet:
            print(f"    Unmet for {courier.name}:")
            for u in unmet:
                print(f"      ✗ {u}")
        else:
            print(f"    ✓ Available for {courier.name}")

    print()


def _fmt_req(req):
    """Format a single requirement for display."""
    from fnv_planner.models.perk import (
        LevelRequirement,
        PerkRequirement,
        SexRequirement,
        SkillRequirement,
    )
    if isinstance(req, SkillRequirement):
        return f"{req.name} {req.operator} {req.value}"
    if isinstance(req, PerkRequirement):
        return f"Perk {req.perk_form_id:#x} rank {req.rank}"
    if isinstance(req, LevelRequirement):
        return f"Level {req.operator} {req.value}"
    if isinstance(req, SexRequirement):
        return f"Sex: {req.name}"
    return str(req)


if __name__ == "__main__":
    main()
