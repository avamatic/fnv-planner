"""Bootstrap helpers for loading planner data into UI runtime state."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import re

from fnv_planner.engine.build_engine import BuildEngine
from fnv_planner.engine.ui_model import BuildUiModel
from fnv_planner.graph.dependency_graph import DependencyGraph
from fnv_planner.models.constants import ACTOR_VALUE_NAMES, ActorValue
from fnv_planner.models.avif import ActorValueInfo
from fnv_planner.models.game_settings import GameSettings
from fnv_planner.models.item import Armor, Weapon
from fnv_planner.models.perk import Perk
from fnv_planner.parser.avif_parser import parse_all_avifs
from fnv_planner.parser.book_stats import (
    placed_skill_book_copies_by_actor_value,
    skill_books_by_actor_value,
)
from fnv_planner.parser.effect_resolver import EffectResolver
from fnv_planner.parser.item_parser import parse_all_armors, parse_all_books, parse_all_weapons
from fnv_planner.parser.perk_classification import detect_challenge_perk_ids
from fnv_planner.parser.perk_parser import parse_all_perks
from fnv_planner.parser.plugin_merge import (
    banner_title_for_game,
    detect_game_variant,
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


def _default_esm_candidates() -> list[Path]:
    """Return likely Fallout NV/FO3 plugin locations across environments."""
    env_path = os.environ.get("FNV_ESM") or os.environ.get("FALLOUT_ESM")
    candidates: list[Path] = []
    if env_path:
        candidates.append(Path(env_path).expanduser())

    home = Path.home()
    repo_root = Path(__file__).resolve().parents[3]
    candidates.extend(
        [
            # Repo-local game data drop.
            repo_root / "NV_GAME_FILES/Data/FalloutNV.esm",
            # SteamCMD/manual install (common local path on macOS setups).
            home / "Games/FNV/Data/FalloutNV.esm",
            # Native Linux Steam install.
            home / ".local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm",
            # Wine/Proton-style path if Steam libraries are mirrored under home.
            home / ".steam/steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm",
            # Common Fallout 3 installs.
            home / "Games/FO3/Data/Fallout3.esm",
            home / ".local/share/Steam/steamapps/common/Fallout 3 goty/Data/Fallout3.esm",
            home / ".local/share/Steam/steamapps/common/Fallout 3/Data/Fallout3.esm",
            home / ".steam/steam/steamapps/common/Fallout 3 goty/Data/Fallout3.esm",
            home / ".steam/steam/steamapps/common/Fallout 3/Data/Fallout3.esm",
        ]
    )
    return candidates


def _split_path_list(raw: str) -> list[str]:
    values = [raw]
    if os.pathsep and os.pathsep not in {",", ";"}:
        next_values: list[str] = []
        for item in values:
            next_values.extend(item.split(os.pathsep))
        values = next_values

    parts: list[str] = []
    for item in values:
        parts.extend(re.split(r"[\n,;]+", item))
    return [p.strip() for p in parts if p.strip()]


def _env_plugin_paths() -> list[Path] | None:
    raw = os.environ.get("FALLOUT_PLUGINS") or os.environ.get("FNV_PLUGINS")
    if not raw:
        return None
    return [Path(value).expanduser() for value in _split_path_list(raw)]

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
    av_descriptions_by_av: dict[int, str]
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


def _normalize_token(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", text.lower())


def _avif_descriptions_by_actor_value(avifs: list[ActorValueInfo]) -> dict[int, str]:
    by_token: dict[str, str] = {}
    for avif in avifs:
        desc = (avif.description or "").strip()
        if not desc:
            continue
        name_token = _normalize_token(avif.name)
        if name_token:
            by_token[name_token] = desc
        if avif.editor_id.startswith("AV"):
            edid_token = _normalize_token(avif.editor_id[2:])
            if edid_token:
                by_token[edid_token] = desc

    out: dict[int, str] = {}
    for av, name in ACTOR_VALUE_NAMES.items():
        token = _normalize_token(name)
        desc = by_token.get(token)
        if desc:
            out[int(av)] = desc
    return out


def bootstrap_default_session(
    explicit_plugin_paths: list[Path] | None = None,
) -> tuple[BuildSession, UiState]:
    """Build a UI session using default vanilla plugin resolution."""
    plugin_datas: list[bytes] = []
    source = PluginSourceState(mode="defaults")
    game_variant = "fallout-nv"

    paths: list[Path] = []
    if explicit_plugin_paths:
        paths, _missing, _is_explicit = resolve_plugins_for_cli(
            explicit_plugin_paths, explicit_plugin_paths[0]
        )
        source = PluginSourceState(mode="explicit-plugin-list", primary_esm=paths[0])
    else:
        env_paths = _env_plugin_paths()
        if env_paths:
            paths, _missing, _is_explicit = resolve_plugins_for_cli(env_paths, env_paths[0])
            source = PluginSourceState(mode="env-plugin-list", primary_esm=paths[0])
        else:
            for candidate in _default_esm_candidates():
                try:
                    paths, _missing, _is_explicit = resolve_plugins_for_cli(None, candidate)
                    break
                except FileNotFoundError:
                    continue

    if paths:
        plugin_datas = load_plugin_bytes(paths)
        if source.mode == "defaults":
            source = PluginSourceState(mode="default-vanilla-order", primary_esm=paths[0])
        game_variant = detect_game_variant(paths, plugin_dir=paths[0].parent)

    if not plugin_datas:
        gmst = GameSettings.defaults()
        perk_list: list[Perk] = []
        challenge_perk_ids: set[int] = set()
        armors: dict[int, Armor] = {}
        weapons: dict[int, Weapon] = {}
        skill_books_by_av: dict[int, int] = {}
        linked_spells: dict[int, str] = {}
        linked_spell_bonuses: dict[int, dict[int, float]] = {}
        av_descriptions_by_av: dict[int, str] = {}
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
        avifs = parse_records_merged(plugin_datas, parse_all_avifs, missing_group_ok=True)
        av_descriptions_by_av = _avif_descriptions_by_actor_value(avifs)

    graph = DependencyGraph.build(perk_list)
    engine = BuildEngine.new_build(gmst, graph)
    _init_default_build(engine)

    ui_model = BuildUiModel(engine, armors=armors, weapons=weapons)
    perks = {p.form_id: p for p in perk_list}
    state = UiState(
        build_name="Untitled Build",
        target_level=engine.state.target_level,
        max_level=engine.max_level,
        game_variant=game_variant,
        banner_title=banner_title_for_game(game_variant),
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
        av_descriptions_by_av,
        armors,
        weapons,
    ), state
