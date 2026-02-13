"""Parse SPEL records into minimal spell descriptors."""

from __future__ import annotations

import struct

from fnv_planner.models.effect import MagicEffect
from fnv_planner.models.spell import Spell
from fnv_planner.models.spell import SpellEffect
from fnv_planner.parser.effect_parser import parse_all_mgefs
from fnv_planner.models.records import Record
from fnv_planner.parser.plugin_merge import parse_records_merged
from fnv_planner.parser.record_reader import read_grup


def parse_spell(record: Record) -> Spell:
    editor_id = ""
    name = ""
    effects: list[SpellEffect] = []
    pending_mgef_id: int | None = None
    has_conditions = False
    for sub in record.subrecords:
        if sub.type == "EDID":
            editor_id = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
        elif sub.type == "FULL":
            name = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
        elif sub.type == "CTDA":
            # Keep condition semantics conservative for planning:
            # any CTDA means effect is situational, not guaranteed baseline.
            has_conditions = True
        elif sub.type == "EFID" and len(sub.data) >= 4:
            pending_mgef_id = struct.unpack_from("<I", sub.data, 0)[0]
        elif sub.type == "EFIT" and pending_mgef_id is not None and len(sub.data) >= 20:
            magnitude = float(struct.unpack_from("<I", sub.data, 0)[0])
            actor_value = struct.unpack_from("<i", sub.data, 16)[0]
            effects.append(
                SpellEffect(
                    mgef_form_id=int(pending_mgef_id),
                    magnitude=magnitude,
                    actor_value=int(actor_value),
                )
            )
            pending_mgef_id = None
    return Spell(
        form_id=record.header.form_id,
        editor_id=editor_id,
        name=name or editor_id,
        effects=effects,
        has_conditions=has_conditions,
    )


def parse_all_spells(data: bytes) -> list[Spell]:
    records = read_grup(data, "SPEL", all_groups=True)
    return [parse_spell(r) for r in records]


def linked_spell_names_by_form(
    plugin_datas: list[bytes],
    *,
    include_conditional: bool = False,
) -> dict[int, str]:
    spells = parse_records_merged(plugin_datas, parse_all_spells, missing_group_ok=True)
    return {
        int(s.form_id): s.name
        for s in spells
        if s.name and (include_conditional or not s.has_conditions)
    }


def linked_spell_stat_bonuses_by_form(
    plugin_datas: list[bytes],
    *,
    include_conditional: bool = False,
) -> dict[int, dict[int, float]]:
    """Resolve SPEL EFID/EFIT entries into actor-value bonus maps."""
    spells = parse_records_merged(plugin_datas, parse_all_spells, missing_group_ok=True)
    mgefs: dict[int, MagicEffect] = {
        int(m.form_id): m for m in parse_records_merged(plugin_datas, parse_all_mgefs, missing_group_ok=True)
    }
    out: dict[int, dict[int, float]] = {}
    for spell in spells:
        if spell.has_conditions and not include_conditional:
            continue
        bonuses: dict[int, float] = {}
        for eff in spell.effects:
            mgef = mgefs.get(int(eff.mgef_form_id))
            if mgef is None or not mgef.is_value_modifier:
                continue
            av = int(mgef.actor_value)
            if av < 0:
                continue
            bonuses[av] = bonuses.get(av, 0.0) + float(eff.magnitude)
        if bonuses:
            out[int(spell.form_id)] = bonuses
    return out
