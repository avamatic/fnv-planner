"""Helpers for merging parsed records across plugin load order.

Input order matters: later plugins override earlier ones ("last wins").
"""

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TypeVar

from fnv_planner.parser.gmst_parser import parse_all_gmsts


T = TypeVar("T")
K = TypeVar("K")
V = TypeVar("V")

VANILLA_PLUGIN_ORDER: tuple[str, ...] = (
    "FalloutNV.esm",
    "DeadMoney.esm",
    "HonestHearts.esm",
    "OldWorldBlues.esm",
    "LonesomeRoad.esm",
    "GunRunnersArsenal.esm",
    "CaravanPack.esm",
    "ClassicPack.esm",
    "MercenaryPack.esm",
    "TribalPack.esm",
)

LEVEL_CAP_DLCS: tuple[str, ...] = (
    "DeadMoney.esm",
    "HonestHearts.esm",
    "OldWorldBlues.esm",
    "LonesomeRoad.esm",
)

GAME_FALLOUT_3 = "fallout-3"
GAME_FALLOUT_NV = "fallout-nv"
GAME_TTW = "ttw"


def is_missing_grup_error(exc: Exception) -> bool:
    msg = str(exc)
    return isinstance(exc, ValueError) and "GRUP" in msg and "not found in plugin" in msg


def load_plugin_bytes(paths: Iterable[Path]) -> list[bytes]:
    return [p.read_bytes() for p in paths]


def default_vanilla_plugins(primary_esm_path: Path) -> tuple[list[Path], list[Path]]:
    """Return (existing, missing) default vanilla plugin paths in load order."""
    data_dir = primary_esm_path.parent
    ordered = [data_dir / name for name in VANILLA_PLUGIN_ORDER]
    existing = [p for p in ordered if p.exists()]
    missing = [p for p in ordered if not p.exists()]
    # Graceful fallback if only base game exists at a non-standard name/path.
    if not existing and primary_esm_path.exists():
        return [primary_esm_path], []
    return existing, missing


def resolve_plugins_for_cli(
    explicit_paths: list[Path] | None,
    default_primary_esm_path: Path,
) -> tuple[list[Path], list[Path], bool]:
    """Resolve plugin paths for CLI scripts.

    Returns:
        (existing_paths, missing_default_paths, is_explicit)

    Behavior:
      - If explicit paths are provided, all must exist or FileNotFoundError is raised.
      - If explicit paths are not provided, use default vanilla order and return
        existing + missing defaults separately.
    """
    if explicit_paths:
        missing = [p for p in explicit_paths if not p.exists()]
        if missing:
            raise FileNotFoundError(
                "Missing explicit plugins: " + ", ".join(str(p) for p in missing)
            )
        return explicit_paths, [], True

    existing, missing = default_vanilla_plugins(default_primary_esm_path)
    if not existing:
        raise FileNotFoundError(
            "No default plugins found. Pass --esm explicitly."
        )
    return existing, missing, False


def effective_vanilla_level_cap(
    plugin_paths: list[Path],
    gmst_cap: int,
    has_non_base_cap_override: bool = False,
) -> int:
    """Return effective vanilla level cap from loaded plugin names.

    Fallout: New Vegas base cap is 30. Each story DLC increases the cap by +5.
    If a non-base plugin explicitly overrides iMaxCharacterLevel, preserve GMST.
    """
    if has_non_base_cap_override:
        return gmst_cap

    names = {p.name.lower() for p in plugin_paths}
    if "falloutnv.esm" not in names:
        return gmst_cap
    present_dlc = sum(1 for dlc in LEVEL_CAP_DLCS if dlc.lower() in names)
    vanilla_runtime_cap = 30 + (present_dlc * 5)
    return max(gmst_cap, vanilla_runtime_cap)


def has_non_base_level_cap_override(
    plugin_paths: list[Path],
    plugin_datas: list[bytes],
) -> bool:
    """True if a non-FalloutNV plugin explicitly sets iMaxCharacterLevel."""
    for path, data in zip(plugin_paths, plugin_datas):
        try:
            gmsts = parse_all_gmsts(data)
        except Exception as exc:
            if is_missing_grup_error(exc):
                continue
            raise
        if "iMaxCharacterLevel" not in gmsts:
            continue
        if path.name.lower() != "falloutnv.esm":
            return True
    return False


def detect_game_variant(
    plugin_paths: Iterable[Path],
    *,
    plugin_dir: Path | None = None,
) -> str:
    """Infer game variant from loaded plugin names and optional data directory."""
    names = {p.name.lower() for p in plugin_paths}
    if plugin_dir is not None:
        names.update(p.name.lower() for p in plugin_dir.glob("*.esm"))
        names.update(p.name.lower() for p in plugin_dir.glob("*.esp"))

    has_nv = "falloutnv.esm" in names
    has_fo3 = "fallout3.esm" in names
    has_ttw = "taleoftwowastelands.esm" in names or "ttw.esm" in names

    if has_ttw or (has_nv and has_fo3):
        return GAME_TTW
    if has_fo3:
        return GAME_FALLOUT_3
    if has_nv:
        return GAME_FALLOUT_NV
    return GAME_FALLOUT_NV


def banner_title_for_game(game_variant: str) -> str:
    if game_variant == GAME_TTW:
        return "Tee Tee Double UWU"
    if game_variant == GAME_FALLOUT_3:
        return "FO3 Planner"
    return "FNV Planner"


def parse_records_merged(
    plugin_datas: Iterable[bytes],
    parser_fn: Callable[[bytes], list[T]],
    *,
    key_fn: Callable[[T], K] = lambda x: getattr(x, "form_id"),  # type: ignore[arg-type]
    missing_group_ok: bool = True,
) -> list[T]:
    merged: dict[K, T] = {}
    for data in plugin_datas:
        try:
            rows = parser_fn(data)
        except Exception as exc:
            if missing_group_ok and is_missing_grup_error(exc):
                continue
            raise
        for row in rows:
            merged[key_fn(row)] = row
    return list(merged.values())


def parse_dict_merged(
    plugin_datas: Iterable[bytes],
    parser_fn: Callable[[bytes], dict[K, V]],
    *,
    missing_group_ok: bool = True,
) -> dict[K, V]:
    merged: dict[K, V] = {}
    for data in plugin_datas:
        try:
            values = parser_fn(data)
        except Exception as exc:
            if missing_group_ok and is_missing_grup_error(exc):
                continue
            raise
        merged.update(values)
    return merged
