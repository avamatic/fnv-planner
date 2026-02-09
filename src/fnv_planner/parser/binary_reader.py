"""Low-level binary reader with typed read methods and a moving cursor."""

import struct


class BinaryReader:
    """Wraps a bytes buffer with typed reads and a moving cursor.

    Key design: slice(size) returns a new BinaryReader bounded to the next
    `size` bytes. This lets record parsers read freely without overrunning
    into the next record.
    """

    __slots__ = ("_data", "_pos", "_end")

    def __init__(self, data: bytes, offset: int = 0, end: int | None = None) -> None:
        self._data = data
        self._pos = offset
        self._end = end if end is not None else len(data)

    @property
    def position(self) -> int:
        return self._pos

    @property
    def remaining(self) -> int:
        return self._end - self._pos

    def _read(self, size: int) -> bytes:
        if self._pos + size > self._end:
            raise ValueError(
                f"Read of {size} bytes at offset {self._pos} "
                f"would exceed boundary at {self._end}"
            )
        chunk = self._data[self._pos : self._pos + size]
        self._pos += size
        return chunk

    def uint8(self) -> int:
        return self._read(1)[0]

    def uint16(self) -> int:
        return struct.unpack_from("<H", self._read(2))[0]

    def uint32(self) -> int:
        return struct.unpack_from("<I", self._read(4))[0]

    def int32(self) -> int:
        return struct.unpack_from("<i", self._read(4))[0]

    def float32(self) -> float:
        return struct.unpack_from("<f", self._read(4))[0]

    def signature(self) -> str:
        """Read a 4-byte ASCII record type signature (e.g. 'PERK', 'GRUP')."""
        return self._read(4).decode("ascii")

    def bytes(self, size: int) -> bytes:
        return self._read(size)

    def cstring(self) -> str:
        """Read a null-terminated string."""
        start = self._pos
        try:
            null = self._data.index(b"\x00", start, self._end)
        except ValueError:
            raise ValueError(f"No null terminator found starting at offset {start}")
        result = self._data[start:null].decode("utf-8", errors="replace")
        self._pos = null + 1  # skip past the null byte
        return result

    def skip(self, size: int) -> None:
        if self._pos + size > self._end:
            raise ValueError(
                f"Skip of {size} bytes at offset {self._pos} "
                f"would exceed boundary at {self._end}"
            )
        self._pos += size

    def slice(self, size: int) -> "BinaryReader":
        """Return a new BinaryReader bounded to the next `size` bytes.

        Advances this reader's cursor past the sliced region.
        """
        if self._pos + size > self._end:
            raise ValueError(
                f"Slice of {size} bytes at offset {self._pos} "
                f"would exceed boundary at {self._end}"
            )
        sub = BinaryReader(self._data, self._pos, self._pos + size)
        self._pos += size
        return sub

    def seek(self, offset: int) -> None:
        """Seek to an absolute position within the bounded region."""
        if offset < 0 or offset > self._end:
            raise ValueError(f"Seek to {offset} is outside bounds [0, {self._end}]")
        self._pos = offset
