"""Controller for the perk-graph ('Cool Stuff') page."""

from dataclasses import dataclass

from fnv_planner.ui.state import UiState


@dataclass(slots=True)
class GraphController:
    """Owns graph-page actions and synchronization."""

    state: UiState

    def refresh(self) -> None:
        """Refresh graph node state and active selection."""
        return

