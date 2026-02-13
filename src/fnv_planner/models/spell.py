"""Spell model for resolving PERK linked-form effects."""

from dataclasses import dataclass, field


@dataclass(slots=True)
class SpellEffect:
    mgef_form_id: int
    magnitude: float
    actor_value: int


@dataclass(slots=True)
class Spell:
    form_id: int
    editor_id: str
    name: str
    effects: list[SpellEffect] = field(default_factory=list)
    has_conditions: bool = False
