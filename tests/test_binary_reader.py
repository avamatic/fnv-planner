"""Tests for BinaryReader — all synthetic bytes, no ESM needed."""

import struct

import pytest

from fnv_planner.parser.binary_reader import BinaryReader


def test_uint8():
    r = BinaryReader(bytes([0x00, 0x7F, 0xFF]))
    assert r.uint8() == 0
    assert r.uint8() == 127
    assert r.uint8() == 255


def test_uint16():
    data = struct.pack("<HH", 0, 0xFFFF)
    r = BinaryReader(data)
    assert r.uint16() == 0
    assert r.uint16() == 65535


def test_uint32():
    data = struct.pack("<II", 42, 0xDEADBEEF)
    r = BinaryReader(data)
    assert r.uint32() == 42
    assert r.uint32() == 0xDEADBEEF


def test_int32():
    data = struct.pack("<ii", -1, 100)
    r = BinaryReader(data)
    assert r.int32() == -1
    assert r.int32() == 100


def test_float32():
    data = struct.pack("<f", 3.14)
    r = BinaryReader(data)
    assert abs(r.float32() - 3.14) < 0.001


def test_signature():
    r = BinaryReader(b"PERK")
    assert r.signature() == "PERK"


def test_cstring():
    r = BinaryReader(b"hello\x00world\x00")
    assert r.cstring() == "hello"
    assert r.cstring() == "world"


def test_cstring_no_null():
    r = BinaryReader(b"no null")
    with pytest.raises(ValueError, match="No null terminator"):
        r.cstring()


def test_bytes():
    data = b"\x01\x02\x03\x04"
    r = BinaryReader(data)
    assert r.bytes(2) == b"\x01\x02"
    assert r.bytes(2) == b"\x03\x04"


def test_skip():
    data = struct.pack("<III", 1, 2, 3)
    r = BinaryReader(data)
    r.skip(4)
    assert r.uint32() == 2


def test_remaining_and_position():
    r = BinaryReader(b"abcdef")
    assert r.position == 0
    assert r.remaining == 6
    r.skip(2)
    assert r.position == 2
    assert r.remaining == 4


def test_slice_creates_bounded_reader():
    data = struct.pack("<III", 10, 20, 30)
    r = BinaryReader(data)
    sub = r.slice(8)  # covers first two uint32s

    assert sub.uint32() == 10
    assert sub.uint32() == 20
    assert sub.remaining == 0

    # Parent cursor advanced past the slice
    assert r.uint32() == 30


def test_slice_prevents_overread():
    data = struct.pack("<II", 1, 2)
    r = BinaryReader(data)
    sub = r.slice(4)

    sub.uint32()  # OK
    with pytest.raises(ValueError, match="exceed boundary"):
        sub.uint32()  # Should fail — only 4 bytes in the slice


def test_read_past_end():
    r = BinaryReader(b"\x01\x02")
    r.uint16()
    with pytest.raises(ValueError, match="exceed boundary"):
        r.uint16()


def test_skip_past_end():
    r = BinaryReader(b"\x01\x02")
    with pytest.raises(ValueError, match="exceed boundary"):
        r.skip(10)


def test_slice_past_end():
    r = BinaryReader(b"\x01\x02")
    with pytest.raises(ValueError, match="exceed boundary"):
        r.slice(10)


def test_seek():
    data = struct.pack("<III", 100, 200, 300)
    r = BinaryReader(data)
    r.seek(8)
    assert r.uint32() == 300
    r.seek(0)
    assert r.uint32() == 100
