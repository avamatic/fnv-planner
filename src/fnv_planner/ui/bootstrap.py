"""Bootstrap helpers for loading planner data into UI runtime state."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fnv_planner.engine.build_engine import BuildEngine
from fnv_planner.engine.ui_model import BuildUiModel
from fnv_planner.graph.dependency_graph import DependencyGraph
from fnv_planner.models.constants import ActorValue
from fnv_planner.models.game_settings import GameSettings
from fnv_planner.models.item import Armor, Weapon
from fnv_planner.models.perk import Perk
from fnv_planner.parser.book_stats import (
    placed_skill_book_copies_by_actor_value,
    skill_books_by_actor_value,
)
from fnv_planner.parser.effect_resolver import EffectResolver
from fnv_planner.parser.item_parser import parse_all_armors, parse_all_books, parse_all_weapons
from fnv_planner.parser.perk_classification import detect_challenge_perk_ids
from fnv_planner.parser.perk_parser import parse_all_perks
from fnv_planner.parser.plugin_merge import (
    effective_vanilla_level_cap,
    has_non_base_level_cap_override,
    load_plugin_bytes,
    parse_records_merged,
    resolve_plugins_for_cli,
)
from fnv_planner.parser.spell_parser import (
    linked_spell_names_by_form,
    linked_spell_stat_bonuses_by_form,
)
from fnv_planner.ui.state import PluginSourceState, UiState


DEFAULT_ESM = Path(
    "/home/am/.local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm"
)

AV = ActorValue


@dataclass(slots=True)
class BuildSession:
    """Runtime objects needed by UI pages/controllers."""

    engine: BuildEngine
    ui_model: BuildUiModel
    perks: dict[int, Perk]
    challenge_perk_ids: set[int]
    skill_books_by_av: dict[int, int]
    linked_spell_names_by_form: dict[int, str]
    linked_spell_stat_bonuses_by_form: dict[int, dict[int, float]]
    armors: dict[int, Armor]
    weapons: dict[int, Weapon]


def _balanced_special() -> dict[int, int]:
    return {
        int(AV.STRENGTH): 5,
        int(AV.PERCEPTION): 5,
        int(AV.ENDURANCE): 5,
        int(AV.CHARISMA): 5,
        int(AV.INTELLIGENCE): 10,
        int(AV.AGILITY): 5,
        int(AV.LUCK): 5,
    }


def _init_default_build(engine: BuildEngine) -> None:
    engine.set_special(_balanced_special())
    engine.set_sex(0)
    engine.set_tagged_skills({int(AV.GUNS), int(AV.LOCKPICK), int(AV.SPEECH)})
    engine.set_target_level(engine.max_level)


def bootstrap_default_session() -> tuple[BuildSession, UiState]:
    """Build a UI session using default vanilla plugin resolution."""
    plugin_datas: list[bytes] = []
    source = PluginSourceState(mode="defaults")

    try:
        paths, _missing, _is_explicit = resolve_plugins_for_cli(None, DEFAULT_ESM)
    except FileNotFoundError:
        paths = []

    if paths:
        plugin_datas = load_plugin_bytes(paths)
        source = PluginSourceState(mode="default-vanilla-order", primary_esm=paths[0])

    if not plugin_datas:
        gmst = GameSettings.defaults()
        perk_list: list[Perk] = []
        challenge_perk_ids: set[int] = set()
        armors: dict[int, Armor] = {}
        weapons: dict[int, Weapon] = {}
        skill_books_by_av: dict[int, int] = {}
        linked_spells: dict[int, str] = {}
        linked_spell_bonuses: dict[int, dict[int, float]] = {}
    else:
        gmst = GameSettings.from_plugins(plugin_datas)
        if not gmst._values:
            gmst = GameSettings.defaults()
        else:
            has_override = has_non_base_level_cap_override(paths, plugin_datas)
            gmst._values["iMaxCharacterLevel"] = effective_vanilla_level_cap(
                paths,
                gmst.get_int("iMaxCharacterLevel", 50),
                has_non_base_cap_override=has_override,
            )
        perk_list = parse_records_merged(plugin_datas, parse_all_perks, missing_group_ok=True)
        challenge_perk_ids = detect_challenge_perk_ids(plugin_datas, perk_list)

        resolver = EffectResolver.from_plugins(plugin_datas)
        armor_list = parse_records_merged(plugin_datas, parse_all_armors, missing_group_ok=True)
        weapon_list = parse_records_merged(plugin_datas, parse_all_weapons, missing_group_ok=True)
        for armor in armor_list:
            resolver.resolve_armor(armor)
        for weapon in weapon_list:
            resolver.resolve_weapon(weapon)
        armors = {a.form_id: a for a in armor_list if a.is_playable}
        weapons = {w.form_id: w for w in weapon_list if w.is_playable}
        books = parse_records_merged(plugin_datas, parse_all_books, missing_group_ok=True)
        skill_books_by_av = placed_skill_book_copies_by_actor_value(plugin_datas, books)
        if not skill_books_by_av:
            skill_books_by_av = skill_books_by_actor_value(books)
        linked_spells = linked_spell_names_by_form(plugin_datas)
        linked_spell_bonuses = linked_spell_stat_bonuses_by_form(plugin_datas)

    graph = DependencyGraph.build(perk_list)
    engine = BuildEngine.new_build(gmst, graph)
    _init_default_build(engine)

    ui_model = BuildUiModel(engine, armors=armors, weapons=weapons)
    perks = {p.form_id: p for p in perk_list}
    state = UiState(
        build_name="Untitled Build",
        target_level=engine.state.target_level,
        max_level=engine.max_level,
        plugin_source=source,
    )
    return BuildSession(
        engine,
        ui_model,
        perks,
        challenge_perk_ids,
        skill_books_by_av,
        linked_spells,
        linked_spell_bonuses,
        armors,
        weapons,
    ), state
