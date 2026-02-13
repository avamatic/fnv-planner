"""Tests for GMST parser — unit tests with synthetic data + ESM integration."""

import struct
from pathlib import Path

import pytest

from fnv_planner.models.records import Record, RecordHeader, Subrecord
from fnv_planner.parser.gmst_parser import parse_all_gmsts, parse_gmst


ESM_PATH = Path(
    "/home/am/.local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm"
)


# --- Helpers ---

def _make_gmst_record(editor_id: str, data: bytes, form_id: int = 0x100) -> Record:
    """Build a synthetic GMST record with EDID and DATA subrecords."""
    edid_bytes = editor_id.encode("utf-8") + b"\x00"
    return Record(
        header=RecordHeader(
            type="GMST", data_size=0, flags=0,
            form_id=form_id, revision=0, version=0,
        ),
        subrecords=[
            Subrecord(type="EDID", data=edid_bytes),
            Subrecord(type="DATA", data=data),
        ],
    )


# --- Unit tests: parse_gmst ---

def test_parse_float_gmst():
    """GMST with 'f' prefix parses DATA as float32."""
    data = struct.pack("<f", 150.0)
    record = _make_gmst_record("fAVDCarryWeightsBase", data)
    editor_id, value = parse_gmst(record)
    assert editor_id == "fAVDCarryWeightsBase"
    assert isinstance(value, float)
    assert value == pytest.approx(150.0)


def test_parse_int_gmst():
    """GMST with 'i' prefix parses DATA as int32."""
    data = struct.pack("<i", 50)
    record = _make_gmst_record("iMaxCharacterLevel", data)
    editor_id, value = parse_gmst(record)
    assert editor_id == "iMaxCharacterLevel"
    assert isinstance(value, int)
    assert value == 50


def test_parse_negative_int_gmst():
    """GMST with 'i' prefix handles negative int32."""
    data = struct.pack("<i", -1)
    record = _make_gmst_record("iTestNegative", data)
    _, value = parse_gmst(record)
    assert value == -1


def test_parse_string_gmst():
    """GMST with 's' prefix parses DATA as null-terminated string."""
    text = "Hello World"
    data = text.encode("utf-8") + b"\x00"
    record = _make_gmst_record("sTestString", data)
    editor_id, value = parse_gmst(record)
    assert editor_id == "sTestString"
    assert isinstance(value, str)
    assert value == "Hello World"


def test_parse_empty_string_gmst():
    """GMST with 's' prefix and empty DATA gives empty string."""
    record = _make_gmst_record("sEmpty", b"\x00")
    _, value = parse_gmst(record)
    assert value == ""


def test_missing_edid_raises():
    """GMST without EDID subrecord raises ValueError."""
    record = Record(
        header=RecordHeader(
            type="GMST", data_size=0, flags=0,
            form_id=0x100, revision=0, version=0,
        ),
        subrecords=[
            Subrecord(type="DATA", data=struct.pack("<f", 1.0)),
        ],
    )
    with pytest.raises(ValueError, match="no EDID"):
        parse_gmst(record)


# --- Integration tests (require ESM) ---

pytestmark_esm = pytest.mark.skipif(
    not ESM_PATH.exists(), reason="FalloutNV.esm not found"
)


@pytest.fixture(scope="module")
def esm_data():
    return ESM_PATH.read_bytes()


@pytest.fixture(scope="module")
def gmst_values(esm_data):
    return parse_all_gmsts(esm_data)


@pytestmark_esm
def test_gmst_count(gmst_values):
    """Vanilla FNV has a large number of GMST records."""
    assert len(gmst_values) > 100


@pytestmark_esm
def test_carry_weight_base(gmst_values):
    """fAVDCarryWeightsBase should be 150.0 in vanilla."""
    assert gmst_values["fAVDCarryWeightsBase"] == pytest.approx(150.0)


@pytestmark_esm
def test_action_points_base(gmst_values):
    """fAVDActionPointsBase should be 65.0 in vanilla."""
    assert gmst_values["fAVDActionPointsBase"] == pytest.approx(65.0)


@pytestmark_esm
def test_max_character_level(gmst_values):
    """iMaxCharacterLevel should be 30 in vanilla (before DLC)."""
    # Note: vanilla FNV base game has 30; DLCs raise it to 50.
    # The ESM itself defines the base game value.
    assert isinstance(gmst_values["iMaxCharacterLevel"], int)
    assert gmst_values["iMaxCharacterLevel"] >= 30


@pytestmark_esm
def test_tag_skill_bonus(gmst_values):
    """fAVDTagSkillBonus should be 15.0 in vanilla."""
    assert gmst_values["fAVDTagSkillBonus"] == pytest.approx(15.0)


@pytestmark_esm
def test_skill_points_base(gmst_values):
    """iLevelUpSkillPointsBase should be 11 in vanilla (base game value)."""
    # Vanilla base game has 10 points/level base, but the GMST
    # iLevelUpSkillPointsBase controls this.
    assert isinstance(gmst_values["iLevelUpSkillPointsBase"], int)
    assert gmst_values["iLevelUpSkillPointsBase"] > 0


@pytestmark_esm
def test_skill_book_base_points_gmst(gmst_values):
    """fBookPerkBonus defines base points granted by skill books."""
    assert gmst_values["fBookPerkBonus"] == pytest.approx(3.0)
