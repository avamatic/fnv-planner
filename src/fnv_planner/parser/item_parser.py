"""Parse ARMO, WEAP, ALCH, and BOOK records into item models.

Key edge cases handled here:
  - ARMO DNAM: 12 bytes = normal (AR/DT/unknown), 4 bytes = audio template (DT=0)
  - ARMO BMDT: byte 4 bit 6 = non-playable flag. Bytes 5-7 are uninitialized junk.
  - WEAP DATA: 15 bytes packed as IIfHB (value, health, weight, damage, clip_size)
  - WEAP is_playable: header flags bit 2 (0x04) = non-playable
  - ALCH DATA: only 4 bytes (weight as float32) — value lives in ENIT
  - BOOK DATA: 10 bytes — flags(u8) + skill_index(i8) + value(u32) + weight(f32)
"""

import struct

from fnv_planner.models.effect import EffectCondition, EnchantmentEffect
from fnv_planner.models.item import Armor, Book, Consumable, Weapon
from fnv_planner.models.records import Record


_COMPARISON_SYMBOLS: dict[int, str] = {
    0: "==",
    1: "!=",
    2: ">",
    3: ">=",
    4: "<",
    5: "<=",
}


def _decode_ctda(data: bytes) -> EffectCondition:
    type_byte = data[0]
    comp_value = struct.unpack_from("<f", data, 4)[0]
    func_idx = struct.unpack_from("<H", data, 8)[0]
    param1 = struct.unpack_from("<I", data, 12)[0]
    param2 = struct.unpack_from("<I", data, 16)[0]
    comp_op = (type_byte >> 5) & 0x07
    is_or = bool(type_byte & 0x01)
    return EffectCondition(
        function=func_idx,
        operator=_COMPARISON_SYMBOLS.get(comp_op, f"?{comp_op}"),
        value=comp_value,
        param1=param1,
        param2=param2,
        is_or=is_or,
    )


def parse_armor(record: Record) -> Armor:
    """Parse a single ARMO record."""
    editor_id = ""
    name = ""
    value = 0
    health = 0
    weight = 0.0
    dt = 0.0
    equipment_slot = -1
    ench_form_id: int | None = None
    is_playable = True

    for sub in record.subrecords:
        if sub.type == "EDID":
            editor_id = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
        elif sub.type == "FULL":
            name = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
        elif sub.type == "ETYP" and len(sub.data) >= 4:
            equipment_slot = struct.unpack_from("<i", sub.data, 0)[0]
        elif sub.type == "EITM" and len(sub.data) >= 4:
            ench_form_id = struct.unpack_from("<I", sub.data, 0)[0]
        elif sub.type == "BMDT" and len(sub.data) >= 5:
            # Byte 4 bit 6 = non-playable. Ignore bytes 5-7 (uninitialized).
            is_playable = not bool(sub.data[4] & 0x40)
        elif sub.type == "DNAM":
            if len(sub.data) >= 12:
                # Normal: AR (unused), DT, unknown — all float32
                dt = struct.unpack_from("<f", sub.data, 4)[0]
            # 4-byte DNAM = audio template reference, DT stays 0.0
        elif sub.type == "DATA" and len(sub.data) >= 12:
            # value(u32) + health(u32) + weight(f32)
            value, health = struct.unpack_from("<II", sub.data, 0)
            weight = struct.unpack_from("<f", sub.data, 8)[0]

    return Armor(
        form_id=record.header.form_id,
        editor_id=editor_id,
        name=name or editor_id,
        value=value,
        health=health,
        weight=weight,
        damage_threshold=dt,
        equipment_slot=equipment_slot,
        enchantment_form_id=ench_form_id,
        is_playable=is_playable,
    )


def parse_all_armors(data: bytes) -> list[Armor]:
    """Parse all ARMO records from a plugin file."""
    from fnv_planner.parser.record_reader import read_grup
    return [parse_armor(r) for r in read_grup(data, "ARMO")]


def parse_weapon(record: Record) -> Weapon:
    """Parse a single WEAP record."""
    editor_id = ""
    name = ""
    value = 0
    health = 0
    weight = 0.0
    damage = 0
    clip_size = 0
    crit_damage = 0
    crit_multiplier = 0.0
    equipment_slot = -1
    ench_form_id: int | None = None
    weapon_flags_1 = 0
    weapon_flags_2 = 0
    # Bit 2 (0x04) of record flags = non-playable
    is_playable = not bool(record.header.flags & 0x04)

    for sub in record.subrecords:
        if sub.type == "EDID":
            editor_id = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
        elif sub.type == "FULL":
            name = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
        elif sub.type == "ETYP" and len(sub.data) >= 4:
            equipment_slot = struct.unpack_from("<i", sub.data, 0)[0]
        elif sub.type == "EITM" and len(sub.data) >= 4:
            ench_form_id = struct.unpack_from("<I", sub.data, 0)[0]
        elif sub.type == "DATA" and len(sub.data) >= 15:
            # value(u32) + health(u32) + weight(f32) + damage(u16) + clip_size(u8)
            value, health = struct.unpack_from("<II", sub.data, 0)
            weight = struct.unpack_from("<f", sub.data, 8)[0]
            damage = struct.unpack_from("<H", sub.data, 12)[0]
            clip_size = sub.data[14]
        elif sub.type == "CRDT" and len(sub.data) >= 12:
            # crit_damage(u16) + padding(2) + crit_multiplier(f32) + ...
            crit_damage = struct.unpack_from("<H", sub.data, 0)[0]
            crit_multiplier = struct.unpack_from("<f", sub.data, 4)[0]
        elif sub.type == "DNAM" and len(sub.data) >= 60:
            # DNAM contains WEAP tuning fields including Flags1 (u8) at offset 12
            # and Flags2 (u32) at offset 56.
            weapon_flags_1 = sub.data[12]
            weapon_flags_2 = struct.unpack_from("<I", sub.data, 56)[0]

    return Weapon(
        form_id=record.header.form_id,
        editor_id=editor_id,
        name=name or editor_id,
        value=value,
        health=health,
        weight=weight,
        damage=damage,
        clip_size=clip_size,
        crit_damage=crit_damage,
        crit_multiplier=crit_multiplier,
        equipment_slot=equipment_slot,
        enchantment_form_id=ench_form_id,
        is_playable=is_playable,
        weapon_flags_1=weapon_flags_1,
        weapon_flags_2=weapon_flags_2,
    )


def parse_all_weapons(data: bytes) -> list[Weapon]:
    """Parse all WEAP records from a plugin file."""
    from fnv_planner.parser.record_reader import read_grup
    return [parse_weapon(r) for r in read_grup(data, "WEAP")]


def parse_consumable(record: Record) -> Consumable:
    """Parse a single ALCH record."""
    editor_id = ""
    name = ""
    weight = 0.0
    value = 0
    flags = 0
    withdrawal_effect = 0
    addiction_chance = 0.0
    effects: list[EnchantmentEffect] = []

    pending_mgef_id: int | None = None
    pending_conditions: list[EffectCondition] = []

    for sub in record.subrecords:
        if sub.type == "EDID":
            editor_id = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
        elif sub.type == "FULL":
            name = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
        elif sub.type == "DATA" and len(sub.data) >= 4:
            # ALCH DATA is just weight (float32)
            weight = struct.unpack_from("<f", sub.data, 0)[0]
        elif sub.type == "ENIT" and len(sub.data) >= 16:
            # value(u32) + flags(u8) + unused(3) + withdrawal_effect(u32) + addiction_chance(f32)
            value = struct.unpack_from("<I", sub.data, 0)[0]
            flags = sub.data[4]
            withdrawal_effect = struct.unpack_from("<I", sub.data, 8)[0]
            addiction_chance = struct.unpack_from("<f", sub.data, 12)[0]
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
                conditions=list(pending_conditions),
            ))
            pending_mgef_id = None
            pending_conditions.clear()
        elif sub.type == "CTDA":
            if len(sub.data) >= 28:
                pending_conditions.append(_decode_ctda(sub.data))

    return Consumable(
        form_id=record.header.form_id,
        editor_id=editor_id,
        name=name or editor_id,
        weight=weight,
        value=value,
        flags=flags,
        withdrawal_effect=withdrawal_effect,
        addiction_chance=addiction_chance,
        effects=effects,
    )


def parse_all_consumables(data: bytes) -> list[Consumable]:
    """Parse all ALCH records from a plugin file."""
    from fnv_planner.parser.record_reader import read_grup
    return [parse_consumable(r) for r in read_grup(data, "ALCH")]


def parse_book(record: Record) -> Book:
    """Parse a single BOOK record."""
    editor_id = ""
    name = ""
    value = 0
    weight = 0.0
    skill_index = -1

    for sub in record.subrecords:
        if sub.type == "EDID":
            editor_id = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
        elif sub.type == "FULL":
            name = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
        elif sub.type == "DATA" and len(sub.data) >= 10:
            # flags(u8) + skill_index(i8) + value(u32) + weight(f32)
            skill_index = struct.unpack_from("<b", sub.data, 1)[0]
            value = struct.unpack_from("<I", sub.data, 2)[0]
            weight = struct.unpack_from("<f", sub.data, 6)[0]

    return Book(
        form_id=record.header.form_id,
        editor_id=editor_id,
        name=name or editor_id,
        value=value,
        weight=weight,
        skill_index=skill_index,
    )


def parse_all_books(data: bytes) -> list[Book]:
    """Parse all BOOK records from a plugin file."""
    from fnv_planner.parser.record_reader import read_grup
    return [parse_book(r) for r in read_grup(data, "BOOK")]
