"""Generic ESM/ESP record reader using generators.

Navigates the plugin file structure:
  TES4 header → GRUP → Records → Subrecords

Design: everything is a generator so we never load 500k+ records into memory.
The caller asks for a specific GRUP label and iterates over its records.
"""

import zlib

from fnv_planner.models.records import (
    GroupHeader,
    Record,
    RecordHeader,
    Subrecord,
)
from fnv_planner.parser.binary_reader import BinaryReader


# Sizes in bytes
_RECORD_HEADER_SIZE = 24
_GROUP_HEADER_SIZE = 24


def _read_record_header(reader: BinaryReader) -> RecordHeader:
    return RecordHeader(
        type=reader.signature(),
        data_size=reader.uint32(),
        flags=reader.uint32(),
        form_id=reader.uint32(),
        revision=reader.uint32(),
        version=reader.uint16(),
    )


def _read_group_header(reader: BinaryReader) -> GroupHeader:
    """Read a GRUP header. Assumes the 'GRUP' signature has already been verified."""
    return GroupHeader(
        size=reader.uint32(),
        label=reader.signature(),
        group_type=reader.uint32(),
        stamp=reader.uint32(),
    )


def _parse_subrecords(reader: BinaryReader) -> list[Subrecord]:
    """Parse all subrecords from a bounded reader covering one record's data."""
    subrecords: list[Subrecord] = []
    while reader.remaining > 0:
        sig = reader.signature()
        size = reader.uint16()
        data = reader.bytes(size)
        subrecords.append(Subrecord(type=sig, data=data))
    return subrecords


def _read_record(reader: BinaryReader) -> Record:
    """Read a single record (header + subrecords) at the current position."""
    header = _read_record_header(reader)
    # The version field read consumed 2 bytes, but the header is 24 bytes total.
    # We read: sig(4) + data_size(4) + flags(4) + form_id(4) + revision(4) + version(2) = 22
    # Skip the remaining 2 bytes (unknown field).
    reader.skip(2)

    data_reader = reader.slice(header.data_size)

    if header.is_compressed:
        # First 4 bytes of data = decompressed size, rest is zlib-compressed
        decompressed_size = data_reader.uint32()
        compressed = data_reader.bytes(data_reader.remaining)
        raw = zlib.decompress(compressed, bufsize=decompressed_size)
        data_reader = BinaryReader(raw)

    subrecords = _parse_subrecords(data_reader)
    return Record(header=header, subrecords=subrecords)


def read_grup(
    data: bytes,
    label: str,
    *,
    all_groups: bool = False,
) -> list[Record]:
    """Find a top-level GRUP by label and return all its records.

    Args:
        data: The full plugin file contents.
        label: 4-char GRUP label to find (e.g. "PERK").

    Returns:
        List of Record objects from the matching GRUP. If *all_groups* is True,
        aggregates records from every matching top-level GRUP label.

    Raises:
        ValueError: If the GRUP is not found.
    """
    return list(iter_grup(data, label, all_groups=all_groups))


def iter_grup(
    data: bytes,
    label: str,
    *,
    all_groups: bool = False,
) -> "Generator[Record]":
    """Find a top-level GRUP by label and yield its records.

    Skips the TES4 header, then scans top-level GRUPs. By default, stops
    after the first matching GRUP label (backward-compatible behavior).
    If *all_groups* is True, yields records from every matching top-level
    GRUP label encountered.
    """
    reader = BinaryReader(data)

    # Skip TES4 header: read its data_size, then jump past it
    tes4_sig = reader.signature()
    if tes4_sig != "TES4":
        raise ValueError(f"Expected TES4 header, got {tes4_sig!r}")
    tes4_data_size = reader.uint32()
    # Skip rest of TES4 header (flags + form_id + revision + version + unknown = 16 bytes)
    # plus the record data
    reader.skip(16 + tes4_data_size)

    found = False

    # Scan top-level GRUPs
    while reader.remaining > 0:
        sig = reader.signature()
        if sig != "GRUP":
            raise ValueError(f"Expected GRUP, got {sig!r} at offset {reader.position - 4}")

        group = _read_group_header(reader)
        # Skip the last 4 bytes of the GRUP header (unknown/version field)
        reader.skip(4)

        if group.label == label:
            found = True
            # Yield records from this GRUP
            # Data area = group.size - 24 bytes (header size)
            grup_data = reader.slice(group.size - _GROUP_HEADER_SIZE)
            while grup_data.remaining > 0:
                yield _read_record(grup_data)
            if not all_groups:
                return
            continue

        # Skip this GRUP entirely (size includes the 24-byte header we already read)
        reader.skip(group.size - _GROUP_HEADER_SIZE)

    if not found:
        raise ValueError(f"GRUP {label!r} not found in plugin")
