"""Generic ESM/ESP record data classes."""

from dataclasses import dataclass


@dataclass(slots=True)
class Subrecord:
    """A single subrecord within a record (e.g. EDID, FULL, DATA, CTDA)."""
    type: str        # 4-char ASCII signature
    data: bytes      # raw payload (size is len(data))


@dataclass(slots=True)
class RecordHeader:
    """24-byte record header preceding the record data."""
    type: str        # 4-char signature (e.g. "PERK", "NPC_")
    data_size: int   # size of the record data (after header)
    flags: int       # record flags (bit 18 = compressed)
    form_id: int     # unique form ID
    revision: int
    version: int

    @property
    def is_compressed(self) -> bool:
        return bool(self.flags & 0x0004_0000)


@dataclass(slots=True)
class Record:
    """A parsed record: header + list of subrecords."""
    header: RecordHeader
    subrecords: list[Subrecord]


@dataclass(slots=True)
class GroupHeader:
    """24-byte GRUP header. size includes the header itself."""
    size: int        # total group size (including this 24-byte header)
    label: str       # 4-char label for type-0 groups (e.g. "PERK")
    group_type: int
    stamp: int
