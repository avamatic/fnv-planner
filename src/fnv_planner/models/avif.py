"""Actor Value Info (AVIF) data model."""

from dataclasses import dataclass


@dataclass(slots=True)
class ActorValueInfo:
    """Parsed AVIF record metadata for a single actor value."""

    form_id: int
    editor_id: str
    name: str
    description: str
    abbreviation: str | None = None
    icon_path: str | None = None
