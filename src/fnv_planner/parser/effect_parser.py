"""Parse MGEF and ENCH records into effect models.

MGEF (Magic Effect):
  - EDID: editor ID
  - FULL: display name
  - DATA: 72 bytes — we only need archetype (offset 64, uint32) and
    actor_value (offset 68, int32). The first 64 bytes are flags, visuals,
    and other data not needed for stat planning.

ENCH (Enchantment):
  - EDID: editor ID
  - FULL: display name
  - ENIT: 16 bytes — enchantment type at offset 0 (uint32), rest ignored
  - EFID+EFIT pairs: each effect in the enchantment
    - EFID: 4 bytes — MGEF form ID (uint32)
    - EFIT: 20 bytes — magnitude(u32) + area(u32) + duration(u32) +
      type(u32) + actor_value(i32)
  - CTDA subrecords between pairs are condition-gated effects — skipped
"""

import struct

from fnv_planner.models.effect import (
    Enchantment,
    EnchantmentEffect,
    MagicEffect,
)
from fnv_planner.models.records import Record


def parse_mgef(record: Record) -> MagicEffect:
    """Parse a single MGEF record into a MagicEffect."""
    editor_id = ""
    name = ""
    archetype = -1
    actor_value = -1

    for sub in record.subrecords:
        if sub.type == "EDID":
            editor_id = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
        elif sub.type == "FULL":
            name = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
        elif sub.type == "DATA" and len(sub.data) >= 72:
            # Only read archetype and actor_value from the 72-byte DATA block
            archetype = struct.unpack_from("<I", sub.data, 64)[0]
            actor_value = struct.unpack_from("<i", sub.data, 68)[0]

    return MagicEffect(
        form_id=record.header.form_id,
        editor_id=editor_id,
        name=name or editor_id,
        archetype=archetype,
        actor_value=actor_value,
    )


def parse_all_mgefs(data: bytes) -> list[MagicEffect]:
    """Parse all MGEF records from a plugin file."""
    from fnv_planner.parser.record_reader import read_grup
    return [parse_mgef(r) for r in read_grup(data, "MGEF")]


def parse_ench(record: Record) -> Enchantment:
    """Parse a single ENCH record into an Enchantment."""
    editor_id = ""
    name = ""
    ench_type = 0
    effects: list[EnchantmentEffect] = []

    # EFID/EFIT come in pairs — EFID first, then EFIT
    pending_mgef_id: int | None = None

    for sub in record.subrecords:
        if sub.type == "EDID":
            editor_id = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
        elif sub.type == "FULL":
            name = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
        elif sub.type == "ENIT" and len(sub.data) >= 4:
            ench_type = struct.unpack_from("<I", sub.data, 0)[0]
        elif sub.type == "EFID" and len(sub.data) >= 4:
            pending_mgef_id = struct.unpack_from("<I", sub.data, 0)[0]
        elif sub.type == "EFIT" and len(sub.data) >= 20 and pending_mgef_id is not None:
            mag, area, dur, etype, av = struct.unpack_from("<IIIIi", sub.data, 0)
            effects.append(EnchantmentEffect(
                mgef_form_id=pending_mgef_id,
                magnitude=mag,
                area=area,
                duration=dur,
                effect_type=etype,
                actor_value=av,
            ))
            pending_mgef_id = None
        elif sub.type == "CTDA":
            # Skip condition subrecords between effect pairs
            pass

    return Enchantment(
        form_id=record.header.form_id,
        editor_id=editor_id,
        name=name or editor_id,
        enchantment_type=ench_type,
        effects=effects,
    )


def parse_all_enchs(data: bytes) -> list[Enchantment]:
    """Parse all ENCH records from a plugin file."""
    from fnv_planner.parser.record_reader import read_grup
    return [parse_ench(r) for r in read_grup(data, "ENCH")]
