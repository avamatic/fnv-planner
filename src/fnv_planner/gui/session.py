"""Single-user session manager wrapping a BuildEngine instance."""

from __future__ import annotations

from fnv_planner.engine.build_config import BuildConfig
from fnv_planner.engine.build_engine import BuildEngine
from fnv_planner.graph.dependency_graph import DependencyGraph
from fnv_planner.models.constants import SPECIAL_INDICES, SKILL_INDICES, ActorValue
from fnv_planner.models.derived_stats import CharacterStats
from fnv_planner.models.game_settings import GameSettings


# Default SPECIAL: all 5s (sum 35), leaving 5 points to distribute (budget 40).
_DEFAULT_SPECIAL: dict[int, int] = {
    ActorValue.STRENGTH: 5,
    ActorValue.PERCEPTION: 5,
    ActorValue.ENDURANCE: 5,
    ActorValue.CHARISMA: 5,
    ActorValue.INTELLIGENCE: 5,
    ActorValue.AGILITY: 5,
    ActorValue.LUCK: 5,
}


class SessionManager:
    """Holds a single BuildEngine and provides UI-friendly mutation helpers.

    The engine's ``set_special`` requires the budget to match exactly, which
    doesn't suit incremental +/- buttons.  We keep a working copy of SPECIAL
    values and push them to the engine only when the budget balances.
    """

    __slots__ = ("engine", "graph", "config", "special")

    def __init__(
        self,
        gmst: GameSettings,
        graph: DependencyGraph,
        config: BuildConfig | None = None,
    ) -> None:
        self.config = config or BuildConfig()
        self.graph = graph
        self.engine = BuildEngine.new_build(gmst, graph, self.config)
        # Working SPECIAL — always pushed to engine when budget matches.
        self.special: dict[int, int] = dict(_DEFAULT_SPECIAL)
        self._sync_special()

    # -- SPECIAL helpers ----------------------------------------------------

    @property
    def special_budget(self) -> int:
        return self.config.special_budget

    @property
    def special_spent(self) -> int:
        return sum(self.special.values())

    @property
    def special_remaining(self) -> int:
        return self.special_budget - self.special_spent

    def set_special(self, av: int, value: int) -> bool:
        """Set a SPECIAL stat to a specific value. Returns True if successful."""
        if av not in SPECIAL_INDICES:
            return False
        if value < self.config.special_min or value > self.config.special_max:
            return False
        old = self.special[av]
        self.special[av] = value
        if self.special_spent > self.special_budget:
            self.special[av] = old
            return False
        self._sync_special()
        return True

    def _sync_special(self) -> None:
        """Push working SPECIAL to the engine (bypassing budget validation)."""
        self.engine._state.special = dict(self.special)
        self.engine._invalidate_from(1)

    # -- Name/Sex helpers ---------------------------------------------------

    def set_name(self, name: str) -> None:
        self.engine.set_name(name)

    def set_sex(self, sex: int) -> None:
        self.engine.set_sex(sex)

    # -- Tag helpers --------------------------------------------------------

    def toggle_tag(self, av: int) -> bool:
        """Toggle a tag skill. Returns True if the toggle was applied."""
        if av not in SKILL_INDICES:
            return False
        tags = self.engine._state.tagged_skills
        if av in tags:
            tags.discard(av)
            self.engine._invalidate_from(1)
            return True
        if len(tags) >= self.config.num_tagged_skills:
            return False
        tags.add(av)
        self.engine._invalidate_from(1)
        return True

    # -- Trait helpers ------------------------------------------------------

    def toggle_trait(self, perk_id: int) -> bool:
        """Toggle a trait. Returns True if the toggle was applied."""
        traits = self.engine._state.traits
        if perk_id in traits:
            traits.remove(perk_id)
            self.engine._invalidate_from(1)
            return True
        available = self.graph.available_traits()
        if perk_id not in available:
            return False
        if len(traits) >= self.config.max_traits:
            return False
        traits.append(perk_id)
        self.engine._invalidate_from(1)
        return True

    # -- Queries ------------------------------------------------------------

    def stats(self) -> CharacterStats:
        return self.engine.stats_at(1)

    @property
    def tagged_skills(self) -> set[int]:
        return set(self.engine._state.tagged_skills)

    @property
    def traits(self) -> list[int]:
        return list(self.engine._state.traits)

    @property
    def name(self) -> str:
        return self.engine._state.name

    @property
    def sex(self) -> int | None:
        return self.engine._state.sex
