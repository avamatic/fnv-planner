import struct

from fnv_planner.models.records import Record, RecordHeader, Subrecord
from fnv_planner.models.spell import SpellEffect
from fnv_planner.models.spell import Spell
from fnv_planner.parser.spell_parser import (
    linked_spell_names_by_form,
    linked_spell_stat_bonuses_by_form,
    parse_spell,
)


def _record(subrecords: list[Subrecord]) -> Record:
    return Record(
        header=RecordHeader(
            type="SPEL",
            data_size=0,
            flags=0,
            form_id=0x1234,
            revision=0,
            version=0,
        ),
        subrecords=subrecords,
    )


def _efit_data(*, actor_value: int, magnitude: int) -> bytes:
    buf = bytearray(20)
    struct.pack_into("<I", buf, 0, magnitude)
    struct.pack_into("<i", buf, 16, actor_value)
    return bytes(buf)


def test_parse_spell_marks_conditions_present():
    rec = _record(
        [
            Subrecord(type="EDID", data=b"TestSpell\x00"),
            Subrecord(type="FULL", data=b"Test Spell\x00"),
            Subrecord(type="EFID", data=struct.pack("<I", 0xDEAD)),
            Subrecord(type="EFIT", data=_efit_data(actor_value=42, magnitude=15)),
            Subrecord(type="CTDA", data=b"\x00" * 24),
        ]
    )

    spell = parse_spell(rec)
    assert spell.has_conditions is True
    assert len(spell.effects) == 1


def test_linked_spell_helpers_exclude_conditional_by_default(monkeypatch):
    conditional = Spell(
        form_id=1,
        editor_id="ConditionalSpell",
        name="Conditional",
        effects=[],
        has_conditions=True,
    )
    unconditional = Spell(
        form_id=2,
        editor_id="FlatSpell",
        name="Flat Bonus",
        effects=[],
        has_conditions=False,
    )

    def _fake_parse_records_merged(_plugin_datas, parser_fn, **_kwargs):
        if parser_fn.__name__ == "parse_all_spells":
            return [conditional, unconditional]
        return []

    monkeypatch.setattr("fnv_planner.parser.spell_parser.parse_records_merged", _fake_parse_records_merged)

    names = linked_spell_names_by_form([b"fake"])
    assert names == {2: "Flat Bonus"}
    names_all = linked_spell_names_by_form([b"fake"], include_conditional=True)
    assert names_all == {1: "Conditional", 2: "Flat Bonus"}


def test_linked_spell_bonus_map_excludes_conditional_by_default(monkeypatch):
    conditional = Spell(
        form_id=1,
        editor_id="ConditionalSpell",
        name="Conditional",
        effects=[],
        has_conditions=True,
    )
    unconditional = Spell(
        form_id=2,
        editor_id="FlatSpell",
        name="Flat Bonus",
        effects=[],
        has_conditions=False,
    )

    conditional.effects.append(SpellEffect(mgef_form_id=10, magnitude=15.0, actor_value=42))
    unconditional.effects.append(SpellEffect(mgef_form_id=10, magnitude=3.0, actor_value=32))

    mgef = type("M", (), {"form_id": 10, "is_value_modifier": True, "actor_value": 32})()

    def _fake_parse_records_merged(_plugin_datas, parser_fn, **_kwargs):
        if parser_fn.__name__ == "parse_all_spells":
            return [conditional, unconditional]
        if parser_fn.__name__ == "parse_all_mgefs":
            return [mgef]
        return []

    monkeypatch.setattr("fnv_planner.parser.spell_parser.parse_records_merged", _fake_parse_records_merged)

    bonuses = linked_spell_stat_bonuses_by_form([b"fake"])
    assert bonuses == {2: {32: 3.0}}
    bonuses_all = linked_spell_stat_bonuses_by_form([b"fake"], include_conditional=True)
    assert bonuses_all == {1: {32: 15.0}, 2: {32: 3.0}}
