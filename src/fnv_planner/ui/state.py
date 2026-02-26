"""Shared UI state and lightweight app metadata."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class PluginSourceState:
    """Tracks where plugin data is loaded from."""

    mode: str = "default-vanilla-order"
    primary_esm: Path | None = None


@dataclass(slots=True)
class UiState:
    """Top-level app state used by controllers and views."""

    build_name: str = "Untitled Build"
    target_level: int = 1
    max_level: int = 1
    game_variant: str = "fallout-nv"
    banner_title: str = "FNV Planner"
    plugin_source: PluginSourceState = field(default_factory=PluginSourceState)
