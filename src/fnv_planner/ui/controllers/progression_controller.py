"""Controller for progression-page interactions."""

from dataclasses import dataclass

from fnv_planner.engine.build_engine import BuildEngine
from fnv_planner.engine.ui_model import BuildUiModel, LevelComparison, LevelSnapshot
from fnv_planner.models.constants import ACTOR_VALUE_NAMES
from fnv_planner.models.perk import Perk
from fnv_planner.ui.state import UiState


@dataclass(slots=True)
class ProgressionController:
    """Owns progression-page actions."""

    engine: BuildEngine
    ui_model: BuildUiModel
    perks: dict[int, Perk]
    state: UiState
    from_level: int = 1
    to_level: int | None = None
    active_level: int | None = None
    anytime_perk_labels: list[str] | None = None
    perk_reasons_by_level: dict[int, str] | None = None
    av_descriptions_by_av: dict[int, str] | None = None
    skill_books_needed: int = 0
    skill_books_available: int = 0
    skill_book_rows_data: list[tuple[str, int, int]] | None = None
    skill_book_usage_by_level: dict[int, dict[int, int]] | None = None
    skill_book_points_by_level: dict[int, dict[int, int]] | None = None

    def __post_init__(self) -> None:
        self._sync_bounds()
        if self.to_level is None:
            self.to_level = self.engine.state.target_level

    def refresh(self) -> None:
        """Refresh progression snapshots and deltas."""
        self._sync_bounds()
        if self.to_level is None:
            self.to_level = self.engine.state.target_level
        self.to_level = max(self.from_level, min(self.to_level, self.engine.state.target_level))
        if self.active_level is None:
            self.active_level = self.to_level
        self.active_level = max(self.from_level, min(self.active_level, self.to_level))

    @property
    def max_level(self) -> int:
        return self.engine.max_level

    @property
    def target_level(self) -> int:
        return self.engine.state.target_level

    def set_range(self, from_level: int, to_level: int) -> tuple[bool, str | None]:
        if from_level < 1 or to_level < 1:
            return False, "Levels must be >= 1"
        if from_level > to_level:
            return False, "From level must be <= To level"
        if to_level > self.engine.state.target_level:
            return (
                False,
                f"To level cannot exceed target level ({self.engine.state.target_level})",
            )
        self.from_level = from_level
        self.to_level = to_level
        if self.active_level is None or self.active_level < from_level or self.active_level > to_level:
            self.active_level = to_level
        self.refresh()
        return True, None

    def set_active_level(self, level: int) -> tuple[bool, str | None]:
        if self.to_level is None:
            self.to_level = self.engine.state.target_level
        if level < self.from_level or level > self.to_level:
            return False, f"Active level must be in range L{self.from_level}..L{self.to_level}"
        self.active_level = level
        return True, None

    def progression_rows(self) -> list[LevelSnapshot]:
        self.refresh()
        if self.to_level is None:
            return []
        return self.ui_model.progression(self.from_level, self.to_level)

    def compare_range(self) -> LevelComparison:
        self.refresh()
        if self.to_level is None:
            raise ValueError("Missing to_level")
        return self.ui_model.compare_levels(self.from_level, self.to_level)

    def compare_active_to_target(self) -> LevelComparison:
        self.refresh()
        if self.active_level is None:
            self.active_level = self.target_level
        return self.ui_model.compare_levels(self.active_level, self.target_level)

    def perk_label_for_level(self, level: int, perk_id: int | None) -> str:
        if perk_id is None:
            return "None selected"
        perk = self.perks.get(perk_id)
        if perk is None:
            return f"{perk_id:#x}"
        return f"{perk.name} ({perk_id:#x})"

    def skill_allocation_label_for_level(self, level: int) -> str:
        plan = self.engine.state.level_plans.get(level)
        if plan is None or not plan.skill_points:
            return "No allocation yet"
        parts = []
        for av, pts in sorted(plan.skill_points.items()):
            name = ACTOR_VALUE_NAMES.get(av, f"AV{av}")
            parts.append(f"{name} +{pts}")
        return ", ".join(parts)

    def _sync_bounds(self) -> None:
        self.state.target_level = self.engine.state.target_level
        self.state.max_level = self.engine.max_level

    def set_anytime_perks(self, labels: list[str]) -> None:
        self.anytime_perk_labels = list(labels)

    def set_perk_reasons(self, reasons: dict[int, str]) -> None:
        self.perk_reasons_by_level = {int(level): str(text) for level, text in reasons.items()}

    def perk_reason_for_level(self, level: int) -> str | None:
        if not self.perk_reasons_by_level:
            return None
        return self.perk_reasons_by_level.get(int(level))

    def set_skill_book_usage(
        self,
        needed: int,
        available: int,
        rows: list[tuple[str, int, int]],
        by_level: dict[int, dict[int, int]] | None = None,
        points_by_level: dict[int, dict[int, int]] | None = None,
    ) -> None:
        self.skill_books_needed = max(0, int(needed))
        self.skill_books_available = max(0, int(available))
        self.skill_book_rows_data = [(str(name), int(req), int(have)) for name, req, have in rows]
        self.skill_book_usage_by_level = {
            int(level): {int(av): int(count) for av, count in per_level.items()}
            for level, per_level in (by_level or {}).items()
        }
        self.skill_book_points_by_level = {
            int(level): {int(av): int(points) for av, points in per_level.items()}
            for level, per_level in (points_by_level or {}).items()
        }

    def skill_books_summary(self) -> str:
        rows = self.skill_book_rows_data or []
        if self.skill_books_needed <= 0 and self.skill_books_available <= 0 and not rows:
            return "Skill books: no data"
        if not rows:
            return (
                f"Skill books (plan): {self.skill_books_needed} / {self.skill_books_available}"
            )
        parts: list[str] = []
        for name, needed, available in rows:
            if needed <= 0 and available <= 0:
                continue
            parts.append(f"{name} {needed}/{available}")
        details = ", ".join(parts) if parts else "No per-skill usage"
        return (
            f"Skill books (plan): {self.skill_books_needed} / {self.skill_books_available}"
            f" | {details}"
        )

    def skill_books_timeline_label_for_level(self, level: int) -> str:
        by_level = self.skill_book_usage_by_level or {}
        delta = by_level.get(int(level), {})

        cumulative: dict[int, int] = {}
        for lv in sorted(by_level):
            if int(lv) > int(level):
                break
            for av, count in by_level[lv].items():
                cumulative[int(av)] = cumulative.get(int(av), 0) + max(0, int(count))

        if not delta and not cumulative:
            return "Skill books: none"

        delta_parts: list[str] = []
        for av in sorted(delta):
            name = ACTOR_VALUE_NAMES.get(int(av), f"AV{av}")
            delta_parts.append(f"{name} +{int(delta[av])}")
        cum_parts: list[str] = []
        for av in sorted(cumulative):
            name = ACTOR_VALUE_NAMES.get(int(av), f"AV{av}")
            cum_parts.append(f"{name} {int(cumulative[av])}")

        delta_text = ", ".join(delta_parts) if delta_parts else "none this level"
        cum_text = ", ".join(cum_parts) if cum_parts else "none"
        return f"Skill books: {delta_text} (cumulative: {cum_text})"

    def skill_books_between_levels_label(self, from_level: int, to_level: int) -> str | None:
        if int(to_level) <= 1:
            return None
        count_delta = (self.skill_book_usage_by_level or {}).get(int(to_level), {})
        point_delta = (self.skill_book_points_by_level or {}).get(int(to_level), {})
        if not count_delta and not point_delta:
            return None

        parts: list[str] = []
        for av in sorted(set(count_delta) | set(point_delta)):
            name = ACTOR_VALUE_NAMES.get(int(av), f"AV{av}")
            books = int(count_delta.get(int(av), 0))
            points = int(point_delta.get(int(av), 0))
            parts.append(f"{name} +{books} book(s) (+{points} skill)")
        detail = ", ".join(parts) if parts else "none"
        return f"Between L{int(from_level)} and L{int(to_level)}: {detail}"

    def effective_skills_for_level(
        self,
        level: int,
        base_skills: dict[int, int],
    ) -> dict[int, int]:
        adjusted = {int(av): int(value) for av, value in base_skills.items()}
        points = self._cumulative_book_points_up_to_level(level)
        for av, bonus in points.items():
            if int(av) not in adjusted:
                continue
            adjusted[int(av)] = int(adjusted[int(av)]) + int(bonus)
        return adjusted

    def actor_value_description(self, actor_value: int) -> str | None:
        mapping = self.av_descriptions_by_av or {}
        desc = mapping.get(int(actor_value))
        if not desc:
            return None
        return desc

    def snapshot_stats_tooltip(self) -> str:
        rows: list[str] = []
        for av in (16, 12, 14):
            name = ACTOR_VALUE_NAMES.get(int(av), f"AV{av}")
            desc = self.actor_value_description(int(av))
            if desc:
                rows.append(f"{name}: {desc}")
        return "\n".join(rows)

    def _cumulative_book_points_up_to_level(self, level: int) -> dict[int, int]:
        points_by_level = self.skill_book_points_by_level or {}
        cumulative: dict[int, int] = {}
        for lv in sorted(points_by_level):
            if int(lv) > int(level):
                break
            for av, points in points_by_level[lv].items():
                cumulative[int(av)] = cumulative.get(int(av), 0) + max(0, int(points))
        return cumulative
