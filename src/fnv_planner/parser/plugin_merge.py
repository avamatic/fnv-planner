"""Helpers for merging parsed records across plugin load order.

Input order matters: later plugins override earlier ones ("last wins").
"""

from collections.abc import Callable, Iterable
from pathlib import Path
from typing import TypeVar


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
