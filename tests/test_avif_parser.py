"""Tests for AVIF parser — synthetic records plus ESM integration checks."""

from pathlib import Path

import pytest

from fnv_planner.models.records import Record, RecordHeader, Subrecord
from fnv_planner.parser.avif_parser import parse_all_avifs, parse_avif
from fnv_planner.parser.record_reader import iter_records_of_type


ESM_PATH = Path(
    "/home/am/.local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm"
)


def _make_avif_record(
    *,
    editor_id: str,
    name: str,
    description: str,
    abbreviation: str,
    icon_path: str,
    form_id: int = 0x3E8,
) -> Record:
    return Record(
        header=RecordHeader(
            type="AVIF",
            data_size=0,
            flags=0,
            form_id=form_id,
            revision=0,
            version=0,
        ),
        subrecords=[
            Subrecord(type="EDID", data=editor_id.encode("utf-8") + b"\x00"),
            Subrecord(type="FULL", data=name.encode("utf-8") + b"\x00"),
            Subrecord(type="DESC", data=description.encode("utf-8") + b"\x00"),
            Subrecord(type="ANAM", data=abbreviation.encode("utf-8") + b"\x00"),
            Subrecord(type="ICON", data=icon_path.encode("utf-8") + b"\x00"),
        ],
    )


def test_parse_avif_basic_fields():
    record = _make_avif_record(
        editor_id="AVPoisonResist",
        name="Poison Resistance",
        description="Reduces poison damage.",
        abbreviation="Poison Res.",
        icon_path="Interface/Icons/foo.dds",
    )
    out = parse_avif(record)
    assert out.form_id == 0x3E8
    assert out.editor_id == "AVPoisonResist"
    assert out.name == "Poison Resistance"
    assert out.description == "Reduces poison damage."
    assert out.abbreviation == "Poison Res."
    assert out.icon_path == "Interface/Icons/foo.dds"


pytestmark_esm = pytest.mark.skipif(
    not ESM_PATH.exists(), reason="FalloutNV.esm not found"
)


@pytestmark_esm
def test_parse_all_avifs_integration_contains_core_actor_values():
    avifs = parse_all_avifs(ESM_PATH.read_bytes())
    by_edid = {a.editor_id: a for a in avifs}
    assert len(avifs) >= 60
    assert "AVPoisonResist" in by_edid
    assert "AVRadResist" in by_edid
    assert "AVActionPoints" in by_edid


@pytestmark_esm
def test_avif_records_are_metadata_only_for_formula_audit():
    """AVIF currently exposes labels/help text, not formula coefficients."""
    records = list(iter_records_of_type(ESM_PATH.read_bytes(), "AVIF"))
    known = {"EDID", "FULL", "DESC", "ANAM", "ICON"}
    observed: set[str] = set()
    for record in records:
        for sub in record.subrecords:
            observed.add(sub.type)
    # This constraint guards our mechanics-source assumptions:
    # AVIF content in FNV is descriptive metadata, not derived-stat formulas.
    assert observed <= known
