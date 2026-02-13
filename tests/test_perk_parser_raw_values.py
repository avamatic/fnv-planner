"""Unit tests for preserving raw CTDA float values in typed perk requirements."""

import struct

import pytest

from fnv_planner.models.constants import ConditionFunction
from fnv_planner.models.records import Record, RecordHeader, Subrecord
from fnv_planner.parser.perk_parser import parse_perk


def _ctda(
    *,
    function: int,
    value: float,
    param1: int = 0,
    param2: int = 0,
    operator: int = 3,  # >=
    is_or: bool = False,
) -> bytes:
    type_byte = ((operator & 0x07) << 5) | (0x01 if is_or else 0x00)
    return struct.pack(
        "<B3xfH2xIIII",
        type_byte,
        value,
        function,
        param1,
        param2,
        0,  # run-on
        0,  # reference
    )


def test_typed_requirements_preserve_raw_ctda_float_values():
    rec = Record(
        header=RecordHeader(
            type="PERK",
            data_size=0,
            flags=0,
            form_id=0x1234,
            revision=0,
            version=0,
        ),
        subrecords=[
            Subrecord(type="EDID", data=b"TestPerk\x00"),
            Subrecord(type="FULL", data=b"Test Perk\x00"),
            Subrecord(type="DATA", data=bytes([0, 2, 1, 1, 0])),
            Subrecord(
                type="CTDA",
                data=_ctda(
                    function=ConditionFunction.GET_PERMANENT_ACTOR_VALUE,
                    value=5.75,
                    param1=5,  # Strength
                ),
            ),
            Subrecord(
                type="CTDA",
                data=_ctda(
                    function=ConditionFunction.HAS_PERK,
                    value=1.49,
                    param1=0xDEAD,
                ),
            ),
            Subrecord(
                type="CTDA",
                data=_ctda(
                    function=ConditionFunction.GET_LEVEL,
                    value=3.2,
                ),
            ),
        ],
    )

    perk = parse_perk(rec)
    assert len(perk.skill_requirements) == 1
    assert len(perk.perk_requirements) == 1
    assert len(perk.level_requirements) == 1

    skill = perk.skill_requirements[0]
    assert skill.value == 6
    assert skill.raw_value == pytest.approx(5.75)

    perk_req = perk.perk_requirements[0]
    assert perk_req.rank == 1
    assert perk_req.raw_value == pytest.approx(1.49)

    level = perk.level_requirements[0]
    assert level.value == 3
    assert level.raw_value == pytest.approx(3.2)
