"""Perk dependency graph with requirement evaluation.

Encodes perk prerequisites as a DAG and evaluates them against
Character + CharacterStats to answer "which perks can this character take?"

Requirements are stored in CNF (Conjunctive Normal Form):
  RequirementSet = AND(clause₁, clause₂, ...)
  RequirementClause = OR(req₁, req₂, ...)

The is_or flag on each requirement controls grouping: is_or=False starts
a new AND-clause, is_or=True chains with the previous requirement in the
same typed list.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field

from fnv_planner.models.character import Character
from fnv_planner.models.constants import ACTOR_VALUE_NAMES, SPECIAL_INDICES
from fnv_planner.models.derived_stats import CharacterStats
from fnv_planner.models.perk import (
    LevelRequirement,
    Perk,
    PerkRequirement,
    RawCondition,
    SexRequirement,
    SkillRequirement,
)

# Union of all evaluatable requirement types.
Requirement = SkillRequirement | PerkRequirement | LevelRequirement | SexRequirement


@dataclass(slots=True)
class RequirementClause:
    """OR-group: at least one requirement must be met."""

    requirements: list[Requirement]


@dataclass(slots=True)
class RequirementSet:
    """CNF: every clause must be satisfied."""

    clauses: list[RequirementClause]
    raw_conditions: list[RawCondition] = field(default_factory=list)


@dataclass(slots=True)
class PerkNode:
    """A node in the dependency graph representing a single perk."""

    perk_id: int
    editor_id: str
    name: str
    is_trait: bool
    is_playable: bool
    min_level: int
    ranks: int
    requirements: RequirementSet


# ---------------------------------------------------------------------------
# Builder helpers
# ---------------------------------------------------------------------------


def _build_clauses_from_reqs(reqs: list[Requirement]) -> list[RequirementClause]:
    """Group a flat requirement list into OR-clauses via the is_or flag.

    Rules:
    - is_or=False starts a new clause (AND boundary).
    - is_or=True appends to the current clause (OR within the clause).

    Example: [A, B(or), C] → clauses [(A, B), (C,)]
      meaning: (A OR B) AND C
    """
    if not reqs:
        return []

    clauses: list[RequirementClause] = []
    current: list[Requirement] = []

    for req in reqs:
        if req.is_or and current:
            # Continue the current OR-group.
            current.append(req)
        else:
            # Flush previous clause, start a new one.
            if current:
                clauses.append(RequirementClause(current))
            current = [req]

    if current:
        clauses.append(RequirementClause(current))

    return clauses


def _build_requirement_set(perk: Perk) -> RequirementSet:
    """Convert a Perk's typed requirement lists into a RequirementSet (CNF)."""
    # Prefer ordered requirements when available so OR groups can span
    # different requirement types in original CTDA order.
    if perk.ordered_requirements:
        clauses = _build_clauses_from_reqs(perk.ordered_requirements)
    else:
        clauses = []
        # Backward-compatible fallback for synthetic/unit-test perks.
        # Each typed list is grouped independently.
        clauses.extend(_build_clauses_from_reqs(perk.skill_requirements))
        clauses.extend(_build_clauses_from_reqs(perk.perk_requirements))
        clauses.extend(_build_clauses_from_reqs(perk.level_requirements))

        # Sex requirement is always a single-element clause (never OR'd).
        if perk.sex_requirement is not None:
            clauses.append(RequirementClause([perk.sex_requirement]))

    return RequirementSet(
        clauses=clauses,
        raw_conditions=list(perk.raw_conditions),
    )


# ---------------------------------------------------------------------------
# Evaluation helpers
# ---------------------------------------------------------------------------


def _compare(actual: int | float, operator: str, threshold: int | float) -> bool:
    """Apply a comparison operator string."""
    if operator == ">=":
        return actual >= threshold
    if operator == ">":
        return actual > threshold
    if operator == "==":
        return actual == threshold
    if operator == "!=":
        return actual != threshold
    if operator == "<":
        return actual < threshold
    if operator == "<=":
        return actual <= threshold
    # Unknown operator — fail conservatively.
    return False


def _check_skill_or_special(
    req: SkillRequirement, stats: CharacterStats
) -> bool:
    """Check a SPECIAL or skill threshold against effective stats."""
    if req.actor_value in SPECIAL_INDICES:
        actual = stats.effective_special.get(req.actor_value, 0)
    else:
        actual = stats.skills.get(req.actor_value, 0)
    return _compare(actual, req.operator, req.value)


def _check_perk(req: PerkRequirement, character: Character) -> bool:
    """Check that the character has enough ranks of a required perk."""
    count = 0
    # Count from leveled perks.
    for perk_ids in character.perks.values():
        count += perk_ids.count(req.perk_form_id)
    # Count from traits.
    count += character.traits.count(req.perk_form_id)
    return count >= req.rank


def _check_level(req: LevelRequirement, character: Character) -> bool:
    return _compare(character.level, req.operator, req.value)


def _check_sex(req: SexRequirement, character: Character) -> bool:
    if character.sex is None:
        # Unset sex — cannot satisfy a sex requirement.
        return False
    return character.sex == req.sex


def _evaluate_requirement(
    req: Requirement, character: Character, stats: CharacterStats
) -> bool:
    """Dispatch evaluation by requirement type."""
    if isinstance(req, SkillRequirement):
        return _check_skill_or_special(req, stats)
    if isinstance(req, PerkRequirement):
        return _check_perk(req, character)
    if isinstance(req, LevelRequirement):
        return _check_level(req, character)
    if isinstance(req, SexRequirement):
        return _check_sex(req, character)
    return False  # pragma: no cover


def _evaluate_clause(
    clause: RequirementClause, character: Character, stats: CharacterStats
) -> bool:
    """OR: at least one requirement in the clause must pass."""
    return any(
        _evaluate_requirement(req, character, stats)
        for req in clause.requirements
    )


def _evaluate_requirement_set(
    req_set: RequirementSet, character: Character, stats: CharacterStats
) -> bool:
    """AND: every clause must be satisfied."""
    return all(
        _evaluate_clause(clause, character, stats)
        for clause in req_set.clauses
    )


# ---------------------------------------------------------------------------
# Human-readable unmet descriptions
# ---------------------------------------------------------------------------


def _describe_requirement(req: Requirement) -> str:
    """Return a short human-readable label for a single requirement."""
    if isinstance(req, SkillRequirement):
        return f"{req.name} {req.operator} {req.value}"
    if isinstance(req, PerkRequirement):
        return f"Perk {req.perk_form_id:#x} rank {req.rank}"
    if isinstance(req, LevelRequirement):
        return f"Level {req.operator} {req.value}"
    if isinstance(req, SexRequirement):
        return f"Sex: {req.name}"
    return str(req)  # pragma: no cover


def _describe_clause(clause: RequirementClause) -> str:
    """Describe a clause as a human-readable string."""
    if len(clause.requirements) == 1:
        return _describe_requirement(clause.requirements[0])
    parts = [_describe_requirement(r) for r in clause.requirements]
    return "One of: " + " OR ".join(parts)


# ---------------------------------------------------------------------------
# DependencyGraph
# ---------------------------------------------------------------------------


class DependencyGraph:
    """DAG of perk nodes with requirement evaluation.

    Nodes are perks; edges represent perk-to-perk dependencies (PerkRequirement).
    SPECIAL/skill thresholds are evaluated against CharacterStats, not modelled
    as graph edges.
    """

    __slots__ = ("_nodes", "_perk_deps", "_reverse_deps", "_raw_condition_policy")

    def __init__(self, raw_condition_policy: str = "strict") -> None:
        if raw_condition_policy not in ("strict", "permissive"):
            raise ValueError(
                "raw_condition_policy must be 'strict' or 'permissive'"
            )
        self._nodes: dict[int, PerkNode] = {}
        self._perk_deps: dict[int, list[int]] = defaultdict(list)
        self._reverse_deps: dict[int, list[int]] = defaultdict(list)
        self._raw_condition_policy = raw_condition_policy

    # --- Construction --------------------------------------------------------

    @classmethod
    def build(
        cls,
        perks: list[Perk],
        raw_condition_policy: str = "strict",
    ) -> DependencyGraph:
        """Build the dependency graph from a list of parsed Perk records."""
        graph = cls(raw_condition_policy=raw_condition_policy)

        for perk in perks:
            req_set = _build_requirement_set(perk)
            node = PerkNode(
                perk_id=perk.form_id,
                editor_id=perk.editor_id,
                name=perk.name,
                is_trait=perk.is_trait,
                is_playable=perk.is_playable,
                min_level=perk.min_level,
                ranks=perk.ranks,
                requirements=req_set,
            )
            graph._nodes[perk.form_id] = node

            # Record perk→perk dependency edges.
            for clause in req_set.clauses:
                for req in clause.requirements:
                    if isinstance(req, PerkRequirement):
                        dep_id = req.perk_form_id
                        if dep_id not in graph._perk_deps[perk.form_id]:
                            graph._perk_deps[perk.form_id].append(dep_id)
                        if perk.form_id not in graph._reverse_deps[dep_id]:
                            graph._reverse_deps[dep_id].append(perk.form_id)

        return graph

    # --- Queries -------------------------------------------------------------

    def get_node(self, perk_id: int) -> PerkNode | None:
        """Return the PerkNode for a given perk ID, or None."""
        return self._nodes.get(perk_id)

    def prerequisites_for(self, perk_id: int) -> RequirementSet | None:
        """Return the full RequirementSet for a perk, or None if unknown."""
        node = self._nodes.get(perk_id)
        return node.requirements if node else None

    def dependents_of(self, perk_id: int) -> list[int]:
        """Return perk IDs that depend on the given perk (reverse deps)."""
        return list(self._reverse_deps.get(perk_id, []))

    def perk_chain(self, perk_id: int) -> list[int]:
        """Return transitive perk dependencies (all ancestors), deepest first."""
        visited: set[int] = set()
        order: list[int] = []

        def _dfs(pid: int) -> None:
            if pid in visited:
                return
            visited.add(pid)
            for dep_id in self._perk_deps.get(pid, []):
                _dfs(dep_id)
            order.append(pid)

        for dep_id in self._perk_deps.get(perk_id, []):
            _dfs(dep_id)
        return order

    def topological_order(self) -> list[int]:
        """Return all perk IDs in topological order (dependencies before dependents).

        Uses Kahn's algorithm. Perks with no dependencies come first.
        """
        in_degree: dict[int, int] = {pid: 0 for pid in self._nodes}
        for pid, deps in self._perk_deps.items():
            if pid in self._nodes:
                in_degree.setdefault(pid, 0)
                for dep in deps:
                    if dep in self._nodes:
                        in_degree[pid] = in_degree.get(pid, 0) + 1

        queue: deque[int] = deque(
            pid for pid, deg in sorted(in_degree.items()) if deg == 0
        )
        result: list[int] = []

        while queue:
            pid = queue.popleft()
            result.append(pid)
            for dependent in self._reverse_deps.get(pid, []):
                if dependent in in_degree:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        queue.append(dependent)

        return result

    # --- Eligibility ---------------------------------------------------------

    def can_take_perk(
        self, perk_id: int, character: Character, stats: CharacterStats
    ) -> bool:
        """Check if a character meets all requirements for a perk."""
        node = self._nodes.get(perk_id)
        if node is None:
            return False
        if not node.is_playable:
            return False
        if node.is_trait:
            return False
        # Level gate
        if character.level < node.min_level:
            return False
        # Max rank check
        current_ranks = 0
        for perk_ids in character.perks.values():
            current_ranks += perk_ids.count(perk_id)
        if current_ranks >= node.ranks:
            return False
        if (
            self._raw_condition_policy == "strict"
            and node.requirements.raw_conditions
        ):
            return False
        return _evaluate_requirement_set(node.requirements, character, stats)

    def available_perks(
        self, character: Character, stats: CharacterStats
    ) -> list[int]:
        """Return IDs of all perks the character can currently take."""
        return [
            pid
            for pid in self._nodes
            if self.can_take_perk(pid, character, stats)
        ]

    def available_traits(self) -> list[int]:
        """Return IDs of all playable traits."""
        return [
            pid
            for pid, node in self._nodes.items()
            if node.is_trait and node.is_playable
        ]

    def unmet_requirements(
        self, perk_id: int, character: Character, stats: CharacterStats
    ) -> list[str]:
        """Return human-readable descriptions of unmet requirement clauses."""
        node = self._nodes.get(perk_id)
        if node is None:
            return [f"Unknown perk {perk_id:#x}"]

        unmet: list[str] = []

        if character.level < node.min_level:
            unmet.append(f"Level >= {node.min_level}")

        current_ranks = 0
        for perk_ids in character.perks.values():
            current_ranks += perk_ids.count(perk_id)
        if current_ranks >= node.ranks:
            unmet.append(f"Already at max rank ({node.ranks})")

        for clause in node.requirements.clauses:
            if not _evaluate_clause(clause, character, stats):
                unmet.append(_describe_clause(clause))
        if self._raw_condition_policy == "strict" and node.requirements.raw_conditions:
            unmet.append(
                "Has unsupported raw conditions (strict mode blocks unknown CTDA)"
            )

        return unmet
