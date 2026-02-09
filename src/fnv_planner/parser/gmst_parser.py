"""Parse GMST (Game Setting) records from ESM data.

GMST records are simple key-value pairs used to configure engine formulas.
Each has:
  - EDID: editor ID string (e.g., "fAVDCarryWeightsBase")
  - DATA: value — type determined by first character of editor ID:
      'f' → float32, 'i' → int32, 's' → null-terminated string
"""

import struct

from fnv_planner.models.records import Record


def parse_gmst(record: Record) -> tuple[str, int | float | str]:
    """Parse a single GMST record into (editor_id, value).

    The value type is inferred from the first character of the editor ID:
    'f' → float32, 'i' → int32, 's' → null-terminated string.
    """
    editor_id = ""
    raw_data: bytes = b""

    for sub in record.subrecords:
        if sub.type == "EDID":
            editor_id = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
        elif sub.type == "DATA":
            raw_data = sub.data

    if not editor_id:
        raise ValueError(f"GMST record {record.header.form_id:#x} has no EDID")

    value: int | float | str
    prefix = editor_id[0]
    if prefix == "f" and len(raw_data) >= 4:
        value = struct.unpack_from("<f", raw_data, 0)[0]
    elif prefix == "i" and len(raw_data) >= 4:
        value = struct.unpack_from("<i", raw_data, 0)[0]
    elif prefix == "s":
        value = raw_data.rstrip(b"\x00").decode("utf-8", errors="replace")
    else:
        # Unknown prefix or missing data — store raw as int
        value = struct.unpack_from("<i", raw_data, 0)[0] if len(raw_data) >= 4 else 0

    return editor_id, value


def parse_all_gmsts(data: bytes) -> dict[str, int | float | str]:
    """Parse all GMST records from a plugin file.

    Returns:
        Dict mapping editor ID → value for every GMST in the file.
    """
    from fnv_planner.parser.record_reader import read_grup

    result: dict[str, int | float | str] = {}
    for record in read_grup(data, "GMST"):
        editor_id, value = parse_gmst(record)
        result[editor_id] = value
    return result
