"""Perk data model with typed requirements."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class SkillRequirement:
    """Requires a SPECIAL stat or skill at a certain level.

    Examples: Strength >= 5, Explosives >= 70
    """
    actor_value: int     # ActorValue index
    name: str            # friendly name (e.g. "Strength")
    operator: str        # comparison symbol (e.g. ">=")
    value: int           # threshold (float32 in the file, but always integral)
    is_or: bool = False  # True if this is an OR condition with the previous


@dataclass(slots=True)
class PerkRequirement:
    """Requires another perk (HasPerk condition)."""
    perk_form_id: int
    rank: int            # minimum rank required
    is_or: bool = False


@dataclass(slots=True)
class SexRequirement:
    """Requires a specific sex (GetIsSex condition).

    sex=0 means Male, sex=1 means Female.
    """
    sex: int             # 0 = Male, 1 = Female
    is_or: bool = False

    @property
    def name(self) -> str:
        return "Male" if self.sex == 0 else "Female"


@dataclass(slots=True)
class LevelRequirement:
    """Requires player level (GetLevel condition)."""
    operator: str
    value: int
    is_or: bool = False


@dataclass(slots=True)
class RawCondition:
    """A condition we don't interpret as a typed requirement.

    Stored for completeness — includes things like GetIsReference (NPC checks)
    and other engine filters.
    """
    function: int
    operator: str
    value: float
    param1: int
    param2: int
    is_or: bool = False


@dataclass(slots=True)
class Perk:
    """A parsed PERK record."""
    form_id: int
    editor_id: str
    name: str                              # FULL or fallback to editor_id
    description: str
    is_trait: bool
    min_level: int
    ranks: int
    is_playable: bool
    is_hidden: bool

    # Typed requirements (from CTDAs before first PRKE)
    skill_requirements: list[SkillRequirement] = field(default_factory=list)
    perk_requirements: list[PerkRequirement] = field(default_factory=list)
    sex_requirement: SexRequirement | None = None
    level_requirements: list[LevelRequirement] = field(default_factory=list)
    raw_conditions: list[RawCondition] = field(default_factory=list)
