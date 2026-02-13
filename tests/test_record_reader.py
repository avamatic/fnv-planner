"""Tests for record_reader — synthetic records and real ESM integration."""

import struct
import zlib
from pathlib import Path

import pytest

from fnv_planner.parser.record_reader import iter_grup, read_grup


ESM_PATH = Path(
    "/home/am/.local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm"
)


def _build_tes4_header(data_size: int = 0) -> bytes:
    """Build a minimal TES4 record header with no subrecords."""
    return struct.pack(
        "<4sIIIIHH",
        b"TES4",
        data_size,  # data_size
        0,          # flags
        0,          # form_id
        0,          # revision
        0,          # version
        0,          # unknown
    )


def _build_record(sig: str, form_id: int, subrecords: list[tuple[str, bytes]],
                   flags: int = 0) -> bytes:
    """Build a record with subrecords."""
    # Build subrecord data
    sub_data = b""
    for sub_sig, sub_payload in subrecords:
        sub_data += struct.pack("<4sH", sub_sig.encode("ascii"), len(sub_payload))
        sub_data += sub_payload

    if flags & 0x0004_0000:
        # Compressed: prepend decompressed size, then zlib-compress
        decompressed_size = len(sub_data)
        compressed = zlib.compress(sub_data)
        record_data = struct.pack("<I", decompressed_size) + compressed
    else:
        record_data = sub_data

    header = struct.pack(
        "<4sIIIIHH",
        sig.encode("ascii"),
        len(record_data),
        flags,
        form_id,
        0,  # revision
        0,  # version
        0,  # unknown
    )
    return header + record_data


def _build_grup(label: str, records: list[bytes]) -> bytes:
    """Build a GRUP containing the given record bytes."""
    body = b"".join(records)
    # GRUP header: "GRUP" + size(4) + label(4) + type(4) + stamp(4) + unknown(4)
    size = 24 + len(body)
    header = struct.pack(
        "<4sI4sIII",
        b"GRUP",
        size,
        label.encode("ascii"),
        0,  # group_type
        0,  # stamp
        0,  # unknown
    )
    return header + body


# --- Synthetic tests ---

def test_read_empty_grup():
    data = _build_tes4_header() + _build_grup("TEST", [])
    records = read_grup(data, "TEST")
    assert len(records) == 0


def test_read_single_record():
    rec = _build_record("TEST", 0x100, [("EDID", b"hello\x00")])
    data = _build_tes4_header() + _build_grup("TEST", [rec])
    records = read_grup(data, "TEST")

    assert len(records) == 1
    assert records[0].header.type == "TEST"
    assert records[0].header.form_id == 0x100
    assert len(records[0].subrecords) == 1
    assert records[0].subrecords[0].type == "EDID"
    assert records[0].subrecords[0].data == b"hello\x00"


def test_read_multiple_records():
    recs = [_build_record("TEST", i, [("EDID", f"rec{i}\x00".encode())]) for i in range(3)]
    data = _build_tes4_header() + _build_grup("TEST", recs)
    records = read_grup(data, "TEST")

    assert len(records) == 3
    for i, rec in enumerate(records):
        assert rec.header.form_id == i


def test_skip_non_matching_grup():
    skip_rec = _build_record("SKIP", 1, [("EDID", b"skip\x00")])
    want_rec = _build_record("WANT", 2, [("EDID", b"want\x00")])
    data = (
        _build_tes4_header()
        + _build_grup("SKIP", [skip_rec])
        + _build_grup("WANT", [want_rec])
    )
    records = read_grup(data, "WANT")

    assert len(records) == 1
    assert records[0].header.form_id == 2


def test_repeated_label_defaults_to_first_matching_group():
    rec_a = _build_record("TEST", 1, [("EDID", b"a\x00")])
    rec_b = _build_record("TEST", 2, [("EDID", b"b\x00")])
    data = _build_tes4_header() + _build_grup("TEST", [rec_a]) + _build_grup("TEST", [rec_b])
    records = read_grup(data, "TEST")
    assert [r.header.form_id for r in records] == [1]


def test_repeated_label_can_aggregate_all_groups():
    rec_a = _build_record("TEST", 1, [("EDID", b"a\x00")])
    rec_b = _build_record("TEST", 2, [("EDID", b"b\x00")])
    data = _build_tes4_header() + _build_grup("TEST", [rec_a]) + _build_grup("TEST", [rec_b])
    records = read_grup(data, "TEST", all_groups=True)
    assert [r.header.form_id for r in records] == [1, 2]


def test_iter_grup_all_groups():
    rec_a = _build_record("TEST", 10, [("EDID", b"a\x00")])
    rec_b = _build_record("TEST", 11, [("EDID", b"b\x00")])
    data = _build_tes4_header() + _build_grup("TEST", [rec_a]) + _build_grup("TEST", [rec_b])
    ids = [r.header.form_id for r in iter_grup(data, "TEST", all_groups=True)]
    assert ids == [10, 11]


def test_grup_not_found():
    data = _build_tes4_header() + _build_grup("TEST", [])
    with pytest.raises(ValueError, match="not found"):
        read_grup(data, "NOPE")


def test_bad_tes4_header():
    data = b"NOPE" + b"\x00" * 100
    with pytest.raises(ValueError, match="Expected TES4"):
        read_grup(data, "TEST")


def test_compressed_record():
    rec = _build_record("TEST", 0xFF, [("EDID", b"compressed\x00")], flags=0x0004_0000)
    data = _build_tes4_header() + _build_grup("TEST", [rec])
    records = read_grup(data, "TEST")

    assert len(records) == 1
    assert records[0].header.is_compressed
    assert records[0].subrecords[0].data == b"compressed\x00"


def test_multiple_subrecords():
    rec = _build_record("TEST", 1, [
        ("EDID", b"test\x00"),
        ("FULL", b"Test Name\x00"),
        ("DATA", struct.pack("<I", 42)),
    ])
    data = _build_tes4_header() + _build_grup("TEST", [rec])
    records = read_grup(data, "TEST")

    assert len(records) == 1
    subs = records[0].subrecords
    assert len(subs) == 3
    assert subs[0].type == "EDID"
    assert subs[1].type == "FULL"
    assert subs[2].type == "DATA"
    assert struct.unpack("<I", subs[2].data)[0] == 42


def test_tes4_with_data():
    """TES4 header with actual subrecord data should be skipped properly."""
    tes4_sub = struct.pack("<4sH", b"HEDR", 4) + struct.pack("<I", 0)
    tes4 = _build_tes4_header(data_size=len(tes4_sub))
    # Manually append the TES4 subrecord data after the header
    tes4_full = tes4 + tes4_sub

    rec = _build_record("TEST", 1, [("EDID", b"test\x00")])
    data = tes4_full + _build_grup("TEST", [rec])
    records = read_grup(data, "TEST")

    assert len(records) == 1


def test_iter_grup_is_lazy():
    """iter_grup should yield records one at a time."""
    recs = [_build_record("TEST", i, [("EDID", f"r{i}\x00".encode())]) for i in range(5)]
    data = _build_tes4_header() + _build_grup("TEST", recs)

    gen = iter_grup(data, "TEST")
    first = next(gen)
    assert first.header.form_id == 0
    # Generator should still have more records
    rest = list(gen)
    assert len(rest) == 4


# --- Integration test (requires ESM) ---

@pytest.mark.skipif(not ESM_PATH.exists(), reason="FalloutNV.esm not found")
def test_esm_perk_count():
    """The vanilla ESM should contain exactly 176 PERK records."""
    data = ESM_PATH.read_bytes()
    records = read_grup(data, "PERK")
    assert len(records) == 176

    # Every record should be type PERK
    for rec in records:
        assert rec.header.type == "PERK"

    # Every record should have at least an EDID subrecord
    for rec in records:
        edid_subs = [s for s in rec.subrecords if s.type == "EDID"]
        assert len(edid_subs) == 1, f"FormID 0x{rec.header.form_id:08X} missing EDID"
