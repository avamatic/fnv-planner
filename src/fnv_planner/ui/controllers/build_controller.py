"""Controller for build-page mutations."""

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from fnv_planner.engine.build_engine import BuildEngine
from fnv_planner.engine.ui_model import BuildUiModel, UiDiagnostic
from fnv_planner.models.constants import (
    ACTOR_VALUE_NAMES,
    SKILL_GOVERNING_ATTRIBUTE,
    SKILL_INDICES,
    SPECIAL_INDICES,
)
from fnv_planner.models.derived_stats import CharacterStats
from fnv_planner.models.perk import Perk
from fnv_planner.optimizer.planner import plan_build
from fnv_planner.optimizer.planner import _infer_perk_skill_effects
from fnv_planner.optimizer.specs import GoalSpec, RequirementSpec, StartingConditions
from fnv_planner.parser.perk_classification import classify_perk
from fnv_planner.ui.state import UiState


@dataclass(slots=True)
class PriorityRequest:
    kind: str  # "actor_value" | "perk" | "trait" | "tagged_skill" | "max_skills"
    actor_value: int | None = None
    operator: str = ">="
    value: int | None = None
    perk_id: int | None = None
    perk_rank: int = 1
    trait_id: int | None = None
    tagged_skill_av: int | None = None
    reason: str = ""


@dataclass(slots=True)
class BuildController:
    """Owns build-page actions.

    This controller owns state transitions and read models for the Build page.
    """

    engine: BuildEngine
    ui_model: BuildUiModel
    perks: dict[int, Perk]
    challenge_perk_ids: set[int]
    skill_books_by_av: dict[int, int]
    linked_spell_names_by_form: dict[int, str]
    linked_spell_stat_bonuses_by_form: dict[int, dict[int, float]]
    state: UiState
    av_descriptions_by_av: dict[int, str] = field(default_factory=dict)
    current_level: int = 1
    on_change: Callable[[], None] | None = None
    requests: list[PriorityRequest] | None = None
    _last_feasible: bool = True
    _last_feasibility_message: str = "No priority requests set yet."
    _last_skill_books_used: dict[int, int] = field(default_factory=dict)
    _last_skill_books_used_by_level: dict[int, dict[int, int]] = field(default_factory=dict)
    _last_skill_book_points_by_level: dict[int, dict[int, int]] = field(default_factory=dict)
    _last_perk_selection_reasons: dict[int, str] = field(default_factory=dict)
    _last_book_dependency_warning: str | None = None
    _inferred_effects_by_id: dict[int, object] = field(default_factory=dict)
    quick_perk_preset_path: Path = Path("config/quick_perks.txt")
    real_build_perk_preset_path: Path = Path("config/real_build_perks.txt")

    def __post_init__(self) -> None:
        if self.requests is None:
            self.requests = []
        self._inferred_effects_by_id = {
            int(perk_id): _infer_perk_skill_effects(
                perk,
                linked_spell_names_by_form=self.linked_spell_names_by_form,
                linked_spell_stat_bonuses_by_form=self.linked_spell_stat_bonuses_by_form,
            )
            for perk_id, perk in self.perks.items()
        }
        self._recompute_plan()
        self._sync_state()
        self.current_level = min(max(1, self.current_level), self.state.target_level)

    def refresh(self) -> None:
        """Refresh UI-bound state after any build mutation."""
        self._sync_state()

    @property
    def max_level(self) -> int:
        return self.engine.max_level

    @property
    def target_level(self) -> int:
        return self.engine.state.target_level

    @property
    def special_budget(self) -> int:
        return self.engine.special_budget

    @property
    def special_min(self) -> int:
        return self.engine.special_min

    @property
    def special_max(self) -> int:
        return self.engine.special_max

    def special_values(self) -> dict[int, int]:
        return dict(self.engine.state.special)

    def total_skill_books(self) -> int:
        return sum(max(0, int(v)) for v in self.skill_books_by_av.values())

    def needed_skill_books(self) -> int:
        return sum(max(0, int(v)) for v in self._last_skill_books_used.values())

    def skill_book_rows(self) -> list[tuple[str, int, int]]:
        rows: list[tuple[str, int, int]] = []
        avs = sorted(set(self.skill_books_by_av.keys()) | set(self._last_skill_books_used.keys()))
        for av in avs:
            available = max(0, int(self.skill_books_by_av.get(int(av), 0)))
            needed = max(0, int(self._last_skill_books_used.get(int(av), 0)))
            if available == 0 and needed == 0:
                continue
            name = ACTOR_VALUE_NAMES.get(int(av), f"AV{av}")
            rows.append((name, needed, available))
        return rows

    def skill_book_usage_by_level(self) -> dict[int, dict[int, int]]:
        return {
            int(level): {int(av): int(count) for av, count in per_level.items()}
            for level, per_level in self._last_skill_books_used_by_level.items()
        }

    def skill_book_points_by_level(self) -> dict[int, dict[int, int]]:
        return {
            int(level): {int(av): int(points) for av, points in per_level.items()}
            for level, per_level in self._last_skill_book_points_by_level.items()
        }

    def implant_points_by_level(self) -> dict[int, dict[int, int]]:
        """Estimated SPECIAL points granted by implants before each level-up."""
        special_implants = self._special_implants_by_target_av()
        if not special_implants:
            return {}

        out: dict[int, dict[int, int]] = {}
        used_targets: set[int] = set()

        # Creation-phase implant points are applied before level 2.
        for av, pts in self.engine.state.creation_special_points.items():
            iav = int(av)
            if iav not in special_implants or iav in used_targets:
                continue
            if int(pts) <= 0:
                continue
            out.setdefault(2, {})
            out[2][iav] = out[2].get(iav, 0) + 1
            used_targets.add(iav)

        for level in sorted(self.engine.state.level_plans):
            plan = self.engine.state.level_plans[level]
            for av, pts in plan.special_points.items():
                iav = int(av)
                if iav not in special_implants or iav in used_targets:
                    continue
                if int(pts) <= 0:
                    continue
                out.setdefault(int(level), {})
                out[int(level)][iav] = out[int(level)].get(iav, 0) + 1
                used_targets.add(iav)

        return out

    def perk_reason_for_level(self, level: int) -> str | None:
        reason = self._last_perk_selection_reasons.get(int(level))
        if reason:
            return reason
        return None

    def flat_skill_bonuses_by_level(self) -> dict[int, dict[int, int]]:
        """Cumulative inferred flat skill bonuses active at each level."""
        by_level: dict[int, dict[int, int]] = {}
        active_perks: list[int] = []
        active_traits = [int(tid) for tid in self.engine.state.traits]
        for level in range(1, int(self.engine.state.target_level) + 1):
            if level == 1:
                active_perks.extend(active_traits)
            else:
                plan = self.engine.state.level_plans.get(int(level))
                if plan is not None and plan.perk is not None:
                    active_perks.append(int(plan.perk))

            all_skills = 0
            per_skill: dict[int, int] = {}
            for perk_id in active_perks:
                effects = self._inferred_effects_by_id.get(int(perk_id))
                if effects is None:
                    continue
                all_skills += int(getattr(effects, "all_skills_bonus", 0))
                for av, bonus in getattr(effects, "per_skill_bonus", {}).items():
                    iav = int(av)
                    per_skill[iav] = per_skill.get(iav, 0) + int(bonus)

            level_bonuses: dict[int, int] = {}
            for av in SKILL_INDICES:
                total = int(per_skill.get(int(av), 0)) + all_skills
                if total != 0:
                    level_bonuses[int(av)] = total
            by_level[int(level)] = level_bonuses
        return by_level

    def perk_reasons(self) -> dict[int, str]:
        return dict(self._last_perk_selection_reasons)

    def perk_reason_rows(self) -> list[str]:
        rows: list[str] = []
        for level in sorted(self._last_perk_selection_reasons):
            reason = self._last_perk_selection_reasons[level]
            plan = self.engine.state.level_plans.get(int(level))
            perk_name = "Unknown perk"
            if plan is not None and plan.perk is not None:
                perk = self.perks.get(int(plan.perk))
                perk_name = perk.name if perk is not None else f"{int(plan.perk):#x}"
            rows.append(f"L{int(level)} {perk_name}: {reason}")
        return rows

    def book_dependency_warning(self) -> str | None:
        return self._last_book_dependency_warning

    def actor_value_request_max(self, actor_value: int) -> int:
        if actor_value in SPECIAL_INDICES:
            return self.engine.special_max
        if actor_value in SKILL_INDICES:
            return self.engine.skill_cap
        return 100

    def actor_value_description(self, actor_value: int) -> str | None:
        desc = self.av_descriptions_by_av.get(int(actor_value))
        if not desc:
            return None
        return desc

    @property
    def max_traits(self) -> int:
        return self.engine.max_traits

    def set_target_level(self, level: int) -> tuple[bool, str | None]:
        if level != self.engine.max_level:
            self._recompute_plan()
            self._sync_state()
            self._notify_changed()
            return False, f"Target level is fixed to max level ({self.engine.max_level})."
        self._recompute_plan()
        self._sync_state()
        self._notify_changed()
        return True, None

    def set_preview_level(self, level: int) -> tuple[bool, str | None]:
        if level < 1 or level > self.engine.max_level:
            return False, f"Preview level must be in range 1..{self.engine.max_level}"
        if level > self.engine.state.target_level:
            self._recompute_plan()
        self.current_level = level
        self._sync_state()
        return True, None

    def summary(self) -> tuple[CharacterStats, CharacterStats, dict[str, float], bool]:
        now = self.ui_model.level_snapshot(self.current_level).stats
        target_level = self.engine.state.target_level
        goal = self.ui_model.level_snapshot(target_level).stats
        delta = self.ui_model.compare_levels(self.current_level, target_level).stat_deltas
        return now, goal, delta, self.engine.is_valid()

    def special_totals(self) -> tuple[int, int]:
        used = sum(self.engine.state.special.values())
        return used, self.engine.special_budget - used

    def diagnostics(self) -> list[UiDiagnostic]:
        return self.ui_model.diagnostics(level=self.current_level)

    def trait_options(self) -> list[tuple[int, str]]:
        rows: list[tuple[int, str]] = []
        for perk in sorted(self.perks.values(), key=lambda p: p.name.lower()):
            if not perk.is_trait:
                continue
            rows.append((perk.form_id, perk.name))
        return rows

    def selected_trait_ids(self) -> set[int]:
        assert self.requests is not None
        return {int(r.trait_id) for r in self.requests if r.kind == "trait" and r.trait_id is not None}

    def tagged_skill_options(self) -> list[tuple[int, str]]:
        rows: list[tuple[int, str]] = []
        for av in sorted(int(s) for s in SKILL_GOVERNING_ATTRIBUTE):
            rows.append((int(av), ACTOR_VALUE_NAMES.get(int(av), f"AV{av}")))
        return rows

    def selected_tagged_skill_ids(self) -> set[int]:
        assert self.requests is not None
        return {
            int(r.tagged_skill_av)
            for r in self.requests
            if r.kind == "tagged_skill" and r.tagged_skill_av is not None
        }

    def perk_rows(self, query: str = "") -> list[tuple[int, str, str, bool]]:
        q = query.strip().lower()
        rows: list[tuple[int, str, str, bool]] = []
        sortable: list[tuple[int, int, str, Perk]] = []
        selected_perks = {r.perk_id for r in self.requests if r.kind == "perk"}
        for perk in self.perks.values():
            category = classify_perk(perk, self.challenge_perk_ids).name
            if category not in {"normal", "challenge"}:
                continue
            if q and q not in perk.name.lower() and q not in perk.editor_id.lower():
                continue
            # Keep challenge perks at the bottom of the picker.
            group = 1 if category == "challenge" else 0
            sortable.append((group, perk.min_level, perk.name.lower(), perk))

        for _group, _min_level, _name, perk in sorted(sortable):
            category = classify_perk(perk, self.challenge_perk_ids).name
            rows.append(
                (
                    perk.form_id,
                    perk.name,
                    category,
                    perk.form_id in selected_perks,
                )
            )
        return rows

    def perk_options(self) -> list[tuple[int, str, str]]:
        rows: list[tuple[int, str, str]] = []
        sortable: list[tuple[int, int, str, Perk]] = []
        for perk in self.perks.values():
            category = classify_perk(perk, self.challenge_perk_ids).name
            if category not in {"normal", "challenge"}:
                continue
            group = 1 if category == "challenge" else 0
            sortable.append((group, perk.min_level, perk.name.lower(), perk))
        for _group, _min_level, _name, perk in sorted(sortable):
            category = classify_perk(perk, self.challenge_perk_ids).name
            rows.append((perk.form_id, perk.name, category))
        return rows

    def selected_perk_ids(self) -> set[int]:
        assert self.requests is not None
        return {int(r.perk_id) for r in self.requests if r.kind == "perk" and r.perk_id is not None}

    def set_desired_perk_selected(self, perk_id: int, selected: bool) -> None:
        assert self.requests is not None
        existing_idx = next(
            (i for i, r in enumerate(self.requests) if r.kind == "perk" and r.perk_id == perk_id),
            None,
        )
        if selected:
            if existing_idx is None:
                self.requests.append(
                    PriorityRequest(
                        kind="perk",
                        perk_id=perk_id,
                        perk_rank=1,
                        reason="Perk request",
                    )
                )
        else:
            if existing_idx is not None:
                del self.requests[existing_idx]
        self._recompute_plan()
        self._sync_state()
        self._notify_changed()

    def feasibility_warning(self) -> tuple[bool, str]:
        return self._last_feasible, self._last_feasibility_message

    def anytime_desired_perk_labels(self) -> list[str]:
        assert self.requests is not None
        labels: list[str] = []
        for req in self.requests:
            if req.kind != "perk" or req.perk_id is None:
                continue
            pid = req.perk_id
            perk = self.perks.get(pid)
            if perk is None:
                continue
            category = classify_perk(perk, self.challenge_perk_ids).name
            if category in {"challenge", "special"}:
                labels.append(f"{perk.name} [{category}]")
        return labels

    def actor_value_options(self) -> list[tuple[int, str]]:
        options: list[tuple[int, str]] = []
        for av in sorted(SPECIAL_INDICES | SKILL_INDICES):
            options.append((int(av), ACTOR_VALUE_NAMES.get(int(av), f"AV{av}")))
        return options

    def add_actor_value_request(
        self,
        actor_value: int,
        value: int,
        operator: str = ">=",
        reason: str = "",
    ) -> tuple[bool, str | None]:
        assert self.requests is not None
        if actor_value not in SPECIAL_INDICES and actor_value not in SKILL_INDICES:
            return False, "Unsupported actor value for request"
        self.requests.append(
            PriorityRequest(
                kind="actor_value",
                actor_value=int(actor_value),
                operator=operator,
                value=int(value),
                reason=reason.strip() or "Actor value request",
            )
        )
        self._recompute_plan()
        self._sync_state()
        self._notify_changed()
        return True, None

    def add_perk_request_by_query(self, query: str) -> tuple[bool, str | None]:
        text = query.strip().lower()
        if not text:
            return False, "Enter a perk name or editor ID"
        match: Perk | None = None
        for perk in sorted(self.perks.values(), key=lambda p: p.name.lower()):
            category = classify_perk(perk, self.challenge_perk_ids).name
            if category not in {"normal", "challenge"}:
                continue
            if text == perk.name.lower() or text == perk.editor_id.lower():
                match = perk
                break
            if text in perk.name.lower() or text in perk.editor_id.lower():
                match = perk
                break
        if match is None:
            return False, "No matching perk found"
        self.set_desired_perk_selected(match.form_id, True)
        return True, None

    def set_perk_requests(self, perk_ids: set[int]) -> None:
        assert self.requests is not None
        self.requests = [r for r in self.requests if r.kind != "perk"]
        for pid in sorted(perk_ids):
            self.requests.append(
                PriorityRequest(
                    kind="perk",
                    perk_id=int(pid),
                    perk_rank=1,
                    reason="Perk request",
                )
            )
        self._recompute_plan()
        self._sync_state()
        self._notify_changed()

    def apply_quick_perk_preset(self) -> tuple[bool, str | None]:
        return self._apply_perk_preset(self.quick_perk_preset_path, "quick perk")

    def apply_real_build_perk_preset(self) -> tuple[bool, str | None]:
        return self._apply_perk_preset(self.real_build_perk_preset_path, "real build perk")

    def _apply_perk_preset(self, path: Path, label: str) -> tuple[bool, str | None]:
        if not path.exists():
            return False, f"{label.title()} preset not found: {path}"

        try:
            lines = path.read_text().splitlines()
        except OSError as exc:
            return False, f"Could not read {label} preset: {exc}"

        tokens = [
            line.strip()
            for line in lines
            if line.strip() and not line.strip().startswith("#")
        ]
        if not tokens:
            self.set_perk_requests(set())
            return True, f"{label.title()} preset is empty; cleared perk requests."

        by_edid = {p.editor_id.lower(): int(p.form_id) for p in self.perks.values()}
        by_name = {p.name.lower(): int(p.form_id) for p in self.perks.values()}

        selected: set[int] = set()
        unresolved: list[str] = []
        for tok in tokens:
            raw = tok.strip()
            lowered = raw.lower()
            perk_id: int | None = None
            if lowered in by_edid:
                perk_id = by_edid[lowered]
            elif lowered in by_name:
                perk_id = by_name[lowered]
            elif lowered.startswith("0x"):
                try:
                    perk_id = int(lowered, 16)
                except ValueError:
                    perk_id = None
            elif lowered.isdigit():
                perk_id = int(lowered, 10)

            if perk_id is None or perk_id not in self.perks:
                unresolved.append(raw)
                continue
            selected.add(int(perk_id))

        self.set_perk_requests(selected)

        if unresolved:
            return (
                False,
                f"Applied {label} preset with unresolved entries: "
                + ", ".join(unresolved[:5])
                + (" ..." if len(unresolved) > 5 else ""),
            )
        return True, f"Applied {label} preset ({len(selected)} perks)."

    def add_trait_request_by_query(self, query: str) -> tuple[bool, str | None]:
        text = query.strip().lower()
        if not text:
            return False, "Enter a trait name or editor ID"
        match: Perk | None = None
        for perk in sorted(self.perks.values(), key=lambda p: p.name.lower()):
            if not perk.is_trait:
                continue
            if text == perk.name.lower() or text == perk.editor_id.lower():
                match = perk
                break
            if text in perk.name.lower() or text in perk.editor_id.lower():
                match = perk
                break
        if match is None:
            return False, "No matching trait found"
        assert self.requests is not None
        existing = any(r.kind == "trait" and r.trait_id == match.form_id for r in self.requests)
        if not existing:
            self.requests.append(
                PriorityRequest(
                    kind="trait",
                    trait_id=match.form_id,
                    reason="Trait request",
                )
            )
            self._recompute_plan()
            self._sync_state()
            self._notify_changed()
        return True, None

    def set_trait_requests(self, trait_ids: set[int]) -> tuple[bool, str | None]:
        assert self.requests is not None
        ordered = [tid for tid, _name in self.trait_options() if tid in trait_ids]
        trimmed = ordered[: self.max_traits]
        self.requests = [r for r in self.requests if r.kind != "trait"]
        for tid in trimmed:
            self.requests.append(
                PriorityRequest(
                    kind="trait",
                    trait_id=int(tid),
                    reason="Trait request",
                )
            )
        self._recompute_plan()
        self._sync_state()
        self._notify_changed()
        if len(ordered) > len(trimmed):
            return (
                False,
                f"Trait requests limited to {self.max_traits}; kept first {self.max_traits}.",
            )
        return True, None

    def set_tagged_skill_requests(self, skill_avs: set[int]) -> tuple[bool, str | None]:
        assert self.requests is not None
        ordered = [av for av, _name in self.tagged_skill_options() if av in skill_avs]
        trimmed = ordered[:3]
        self.requests = [r for r in self.requests if r.kind != "tagged_skill"]
        for av in trimmed:
            self.requests.append(
                PriorityRequest(
                    kind="tagged_skill",
                    tagged_skill_av=int(av),
                    reason="Tagged skill request",
                )
            )
        self._recompute_plan()
        self._sync_state()
        self._notify_changed()
        if len(ordered) > len(trimmed):
            return (
                False,
                "Tagged skill requests limited to 3; kept first 3.",
            )
        return True, None

    def add_max_skills_request(self) -> None:
        assert self.requests is not None
        existing = any(r.kind == "max_skills" for r in self.requests)
        if existing:
            return
        self.requests.append(
            PriorityRequest(
                kind="max_skills",
                reason="Max out all skills",
            )
        )
        self._recompute_plan()
        self._sync_state()
        self._notify_changed()

    def priority_request_rows(self) -> list[tuple[int, str]]:
        assert self.requests is not None
        rows: list[tuple[int, str]] = []
        for idx, req in enumerate(self.requests):
            if req.kind == "actor_value":
                av_name = ACTOR_VALUE_NAMES.get(int(req.actor_value or 0), "AV?")
                text = f"{av_name} {req.operator} {req.value} [{req.reason}]"
            elif req.kind == "perk":
                perk_name = self.perks.get(int(req.perk_id or 0)).name if req.perk_id in self.perks else f"{req.perk_id:#x}"
                text = f"Perk: {perk_name} (rank {req.perk_rank}) [{req.reason}]"
            elif req.kind == "trait":
                trait_name = self.perks.get(int(req.trait_id or 0)).name if req.trait_id in self.perks else f"{req.trait_id:#x}"
                text = f"Trait: {trait_name} [{req.reason}]"
            elif req.kind == "tagged_skill":
                av = int(req.tagged_skill_av or 0)
                skill_name = ACTOR_VALUE_NAMES.get(av, f"AV{av}")
                text = f"Tagged Skill: {skill_name} [{req.reason}]"
            elif req.kind == "max_skills":
                text = f"Max Skills: all skills to 100 [{req.reason}]"
            else:
                text = f"Unknown request [{req.reason}]"
            rows.append((idx, text))
        return rows

    def move_priority_request(self, index: int, delta: int) -> None:
        assert self.requests is not None
        new_index = index + delta
        if index < 0 or index >= len(self.requests):
            return
        if new_index < 0 or new_index >= len(self.requests):
            return
        req = self.requests.pop(index)
        self.requests.insert(new_index, req)
        self._recompute_plan()
        self._sync_state()
        self._notify_changed()

    def remove_priority_request(self, index: int) -> None:
        assert self.requests is not None
        if index < 0 or index >= len(self.requests):
            return
        del self.requests[index]
        self._recompute_plan()
        self._sync_state()
        self._notify_changed()

    def special_rows(self) -> list[tuple[int, str, int]]:
        special = self.special_values()
        rows: list[tuple[int, str, int]] = []
        for av in sorted(SPECIAL_INDICES):
            rows.append((av, ACTOR_VALUE_NAMES.get(av, f"AV{av}"), special.get(av, 1)))
        return rows

    def selected_traits_rows(self) -> list[tuple[str, str]]:
        trait_ids = [int(tid) for tid in self.engine.state.traits]
        direct_requested = set(self._requested_traits())
        has_max_skills = any(r.kind == "max_skills" for r in self.requests or [])
        rows: list[tuple[str, str]] = []
        for tid in trait_ids:
            perk = self.perks.get(tid)
            name = perk.name if perk is not None else f"{tid:#x}"
            if tid in direct_requested:
                source = "Direct request"
            elif has_max_skills:
                source = "Auto (Max Skills)"
            else:
                source = "Auto (Derived)"
            rows.append((name, source))
        rows.sort(key=lambda x: x[0].lower())
        return rows

    def selected_tagged_skills_rows(self) -> list[tuple[str, str]]:
        tagged = sorted(int(av) for av in self.engine.state.tagged_skills)
        direct_requested = set(self._requested_tagged_skills())
        has_max_skills = any(r.kind == "max_skills" for r in self.requests or [])
        rows: list[tuple[str, str]] = []
        for av in tagged:
            name = ACTOR_VALUE_NAMES.get(int(av), f"AV{av}")
            if av in direct_requested:
                source = "Direct request"
            elif has_max_skills:
                source = "Auto (Max Skills)"
            else:
                source = "Current build"
            rows.append((name, source))
        return rows

    def selected_perks_rows(self) -> list[tuple[str, int, str]]:
        direct_requested = self.selected_perk_ids()
        has_max_skills = any(r.kind == "max_skills" for r in self.requests or [])
        rows: list[tuple[str, int, str]] = []
        for level in sorted(self.engine.state.level_plans):
            plan = self.engine.state.level_plans[level]
            if plan.perk is None:
                continue
            perk_id = int(plan.perk)
            perk = self.perks.get(perk_id)
            name = perk.name if perk is not None else f"{perk_id:#x}"
            if perk_id in direct_requested:
                source = "Direct request"
            elif has_max_skills:
                source = "Auto (Max Skills)"
            else:
                source = "Auto (Derived)"
            rows.append((name, int(level), source))
        return rows

    def _sync_state(self) -> None:
        self.state.target_level = self.engine.state.target_level
        self.state.max_level = self.engine.max_level

    def _notify_changed(self) -> None:
        if self.on_change is not None:
            self.on_change()

    def _recompute_plan(self) -> None:
        assert self.requests is not None
        state = self.engine.state
        requested_traits = self._requested_traits()
        tagged_skills = self._resolved_tagged_skills(state_tags=set(state.tagged_skills))
        start = StartingConditions(
            name=state.name,
            sex=state.sex,
            special=dict(state.special),
            tagged_skills=tagged_skills,
            traits=requested_traits,
            equipment=dict(state.equipment),
            target_level=self.engine.max_level,
        )
        req_specs = self._requests_as_goal_specs()
        goal = GoalSpec(
            required_perks=[],
            requirements=req_specs,
            skill_books_by_av=dict(self.skill_books_by_av),
            target_level=self.engine.max_level,
            maximize_skills=True,
            fill_perk_slots=False,
        )
        result = plan_build(
            self.engine,
            goal,
            starting=start,
            perks_by_id=self.perks,
            linked_spell_names_by_form=self.linked_spell_names_by_form,
            linked_spell_stat_bonuses_by_form=self.linked_spell_stat_bonuses_by_form,
        )
        self.engine.replace_state(result.state)
        self._last_skill_books_used = dict(result.skill_books_used)
        self._last_skill_books_used_by_level = {
            int(level): {int(av): int(count) for av, count in per_level.items()}
            for level, per_level in result.skill_books_used_by_level.items()
        }
        self._last_skill_book_points_by_level = {
            int(level): {int(av): int(points) for av, points in per_level.items()}
            for level, per_level in result.skill_book_points_by_level.items()
        }
        self._last_perk_selection_reasons = dict(result.perk_selection_reasons)
        self._last_book_dependency_warning = self._derive_book_dependency_warning(
            goal=goal,
            start=start,
            result=result,
        )

        if result.success:
            self._last_feasible = True
            self._last_feasibility_message = "Build possible: all priority requests can be satisfied."
            return

        self._last_feasible = False
        if result.unmet_requirements:
            suffix = "" if len(result.unmet_requirements) <= 2 else " ..."
            self._last_feasibility_message = (
                "Build not possible: " + " | ".join(result.unmet_requirements[:2]) + suffix
            )
        elif result.messages:
            self._last_feasibility_message = "Build not possible: " + result.messages[0]
        else:
            self._last_feasibility_message = "Build not possible with current constraints."

    def _derive_book_dependency_warning(
        self,
        *,
        goal: GoalSpec,
        start: StartingConditions,
        result,
    ) -> str | None:
        if not any(r.kind == "max_skills" for r in goal.requirements):
            return None
        if not result.skill_books_used:
            return None

        book_reason_lines = [
            text for text in self._last_perk_selection_reasons.values()
            if "Books cover +" in text
        ]
        if not book_reason_lines:
            return None

        zero_books_goal = GoalSpec(
            required_perks=list(goal.required_perks),
            requirements=list(goal.requirements),
            skill_books_by_av={},
            target_level=goal.target_level,
            maximize_skills=goal.maximize_skills,
            fill_perk_slots=goal.fill_perk_slots,
        )
        no_books = plan_build(
            self.engine,
            zero_books_goal,
            starting=start,
            perks_by_id=self.perks,
            linked_spell_names_by_form=self.linked_spell_names_by_form,
            linked_spell_stat_bonuses_by_form=self.linked_spell_stat_bonuses_by_form,
        )
        deficit_points = self._extract_max_skills_gap_points(no_books.unmet_requirements)
        books_needed = sum(int(v) for v in result.skill_books_used.values())
        lead = book_reason_lines[0]
        return (
            f"{lead} Book dependency: needs {books_needed} books in this plan; "
            f"without books, max-skills misses by ~{deficit_points} points."
        )

    @staticmethod
    def _extract_max_skills_gap_points(unmet: list[str]) -> int:
        # Parse snippets like "(32:81, 34:81, ...)" and sum (100-value).
        text = " | ".join(unmet)
        pairs = re.findall(r"(\d+):(\d+)", text)
        if not pairs:
            return 0
        total = 0
        for _av, value in pairs:
            total += max(0, 100 - int(value))
        return total

    def _requests_as_goal_specs(self) -> list[RequirementSpec]:
        assert self.requests is not None
        specs: list[RequirementSpec] = []
        total = len(self.requests)
        for idx, req in enumerate(self.requests):
            priority = max(1, total - idx) * 100
            if req.kind == "actor_value" and req.actor_value is not None and req.value is not None:
                specs.append(
                    RequirementSpec(
                        kind="actor_value",
                        priority=priority,
                        reason=req.reason,
                        actor_value=req.actor_value,
                        operator=req.operator,
                        value=req.value,
                    )
                )
            elif req.kind == "perk" and req.perk_id is not None:
                specs.append(
                    RequirementSpec(
                        kind="perk",
                        priority=priority,
                        reason=req.reason,
                        perk_id=req.perk_id,
                        perk_rank=req.perk_rank,
                    )
                )
            elif req.kind == "trait" and req.trait_id is not None:
                specs.append(
                    RequirementSpec(
                        kind="trait",
                        priority=priority,
                        reason=req.reason,
                        trait_id=req.trait_id,
                    )
                )
            elif req.kind == "max_skills":
                specs.append(
                    RequirementSpec(
                        kind="max_skills",
                        priority=priority,
                        reason=req.reason,
                    )
                )
        return specs

    def _requested_traits(self) -> list[int]:
        assert self.requests is not None
        out: list[int] = []
        for req in self.requests:
            if req.kind != "trait" or req.trait_id is None:
                continue
            if req.trait_id in out:
                continue
            out.append(int(req.trait_id))
        return out

    def _requested_tagged_skills(self) -> list[int]:
        assert self.requests is not None
        out: list[int] = []
        for req in self.requests:
            if req.kind != "tagged_skill" or req.tagged_skill_av is None:
                continue
            av = int(req.tagged_skill_av)
            if av not in SKILL_GOVERNING_ATTRIBUTE:
                continue
            if av in out:
                continue
            out.append(av)
        return out

    def _resolved_tagged_skills(self, *, state_tags: set[int]) -> set[int]:
        direct = self._requested_tagged_skills()
        if direct:
            chosen = list(direct)
        elif any(r.kind == "max_skills" for r in (self.requests or [])):
            chosen = self._auto_tagged_skills_for_max_skills()
        else:
            chosen = sorted(int(av) for av in state_tags if int(av) in SKILL_GOVERNING_ATTRIBUTE)

        for av in sorted(int(v) for v in state_tags):
            if av not in SKILL_GOVERNING_ATTRIBUTE or av in chosen:
                continue
            chosen.append(av)
            if len(chosen) >= 3:
                break
        for av in sorted(int(v) for v in SKILL_GOVERNING_ATTRIBUTE):
            if av in chosen:
                continue
            chosen.append(av)
            if len(chosen) >= 3:
                break
        return set(chosen[:3])

    def _auto_tagged_skills_for_max_skills(self) -> list[int]:
        assert self.requests is not None
        ordered: list[int] = []
        # First, prioritize explicit skill targets in request order.
        for req in self.requests:
            if req.kind != "actor_value" or req.actor_value is None:
                continue
            av = int(req.actor_value)
            if av not in SKILL_GOVERNING_ATTRIBUTE or av in ordered:
                continue
            ordered.append(av)
            if len(ordered) >= 3:
                return ordered

        # Then prefer book-starved skills so tags compensate for scarce books.
        candidates = sorted(
            (int(av) for av in SKILL_GOVERNING_ATTRIBUTE),
            key=lambda av: (
                int(self.skill_books_by_av.get(int(av), 0)),
                int(av),
            ),
        )
        for av in candidates:
            if av in ordered:
                continue
            ordered.append(av)
            if len(ordered) >= 3:
                break
        return ordered

    def _special_implants_by_target_av(self) -> dict[int, int]:
        out: dict[int, int] = {}
        for perk in self.perks.values():
            target = self._implant_special_target(perk)
            if target is None:
                continue
            out[int(target)] = int(perk.form_id)
        return out

    @staticmethod
    def _implant_special_target(perk: Perk) -> int | None:
        text = f"{perk.name} {perk.editor_id} {perk.description}".lower()
        if "implant" not in text:
            return None
        mapping = (
            ("strength", 5),
            ("perception", 6),
            ("endurance", 7),
            ("charisma", 8),
            ("intelligence", 9),
            ("agility", 10),
            ("luck", 11),
        )
        for token, av in mapping:
            if token in text:
                return int(av)
        return None
