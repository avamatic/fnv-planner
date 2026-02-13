"""Parse AVIF (Actor Value Info) records from plugin data."""

from fnv_planner.models.avif import ActorValueInfo
from fnv_planner.models.records import Record


def parse_avif(record: Record) -> ActorValueInfo:
    """Parse a single AVIF record."""
    editor_id = ""
    name = ""
    description = ""
    abbreviation: str | None = None
    icon_path: str | None = None

    for sub in record.subrecords:
        if sub.type == "EDID":
            editor_id = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
        elif sub.type == "FULL":
            name = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
        elif sub.type == "DESC":
            description = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
        elif sub.type == "ANAM":
            abbreviation = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
        elif sub.type == "ICON":
            icon_path = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")

    return ActorValueInfo(
        form_id=record.header.form_id,
        editor_id=editor_id,
        name=name or editor_id,
        description=description,
        abbreviation=abbreviation,
        icon_path=icon_path,
    )


def parse_all_avifs(data: bytes) -> list[ActorValueInfo]:
    """Parse all AVIF records from a plugin file."""
    from fnv_planner.parser.record_reader import read_grup

    return [parse_avif(r) for r in read_grup(data, "AVIF")]
