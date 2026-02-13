"""Controller for library-page browse/select flows."""

from dataclasses import dataclass
from typing import Callable

from fnv_planner.engine.build_engine import BuildEngine
from fnv_planner.engine.ui_model import BuildUiModel, CatalogItem
from fnv_planner.models.effect import StatEffect
from fnv_planner.models.item import Armor, Weapon
from fnv_planner.ui.state import UiState


@dataclass(slots=True)
class LibraryController:
    """Owns library page actions."""

    engine: BuildEngine
    ui_model: BuildUiModel
    armors: dict[int, Armor]
    weapons: dict[int, Weapon]
    state: UiState
    on_change: Callable[[], None] | None = None

    def refresh(self) -> None:
        """Refresh query results and selected item inspector."""
        self.state.target_level = self.engine.state.target_level
        self.state.max_level = self.engine.max_level

    def catalog_items(
        self,
        query: str = "",
        include_armor: bool = True,
        include_weapons: bool = True,
    ) -> list[CatalogItem]:
        items = self.ui_model.gear_catalog(query=query)
        filtered: list[CatalogItem] = []
        for item in items:
            if item.kind == "armor" and not include_armor:
                continue
            if item.kind == "weapon" and not include_weapons:
                continue
            filtered.append(item)
        return sorted(filtered, key=lambda it: (it.slot, it.kind, it.name.lower()))

    def get_item(self, form_id: int) -> Armor | Weapon | None:
        if form_id in self.armors:
            return self.armors[form_id]
        if form_id in self.weapons:
            return self.weapons[form_id]
        return None

    def equipped_slots(self) -> list[tuple[int, int, str]]:
        rows: list[tuple[int, int, str]] = []
        for slot, form_id in sorted(self.engine.state.equipment.items()):
            item = self.get_item(form_id)
            if item is None:
                rows.append((slot, form_id, f"Item {form_id:#x}"))
            else:
                rows.append((slot, form_id, item.name))
        return rows

    def equip_catalog_item(self, item: CatalogItem) -> tuple[bool, str | None]:
        self.engine.set_equipment(item.slot, item.form_id)
        self.refresh()
        self._notify_changed()
        return True, None

    def clear_slot(self, slot: int) -> tuple[bool, str | None]:
        self.engine.clear_equipment_slot(slot)
        self.refresh()
        self._notify_changed()
        return True, None

    @staticmethod
    def format_effect(effect: StatEffect) -> str:
        sign = "+" if effect.magnitude >= 0 else ""
        base = f"{sign}{effect.magnitude:g} {effect.actor_value_name}"
        if effect.duration > 0:
            base += f" for {effect.duration}s"
        if effect.is_conditional:
            base += " (conditional)"
        return base

    def _notify_changed(self) -> None:
        if self.on_change is not None:
            self.on_change()
