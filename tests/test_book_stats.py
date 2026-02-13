import struct
from types import SimpleNamespace

from fnv_planner.models.item import Book
from fnv_planner.parser.book_stats import (
    placed_skill_book_copies_by_actor_value,
    skill_books_by_actor_value,
    total_skill_books,
)


def _book(form_id: int, skill_index: int) -> Book:
    return Book(
        form_id=form_id,
        editor_id=f"Book{form_id}",
        name=f"Book {form_id}",
        value=10,
        weight=1.0,
        skill_index=skill_index,
    )


def test_skill_book_counts_by_actor_value():
    books = [
        _book(1, 0),   # Barter
        _book(2, 0),   # Barter
        _book(3, 8),   # Science
        _book(4, -1),  # Non-skill book
    ]
    counts = skill_books_by_actor_value(books)
    assert counts
    assert sum(counts.values()) == 3
    assert total_skill_books(books) == 3


def test_placed_skill_books_include_inventory_templates(monkeypatch):
    # Barter + Science skill books.
    merged_books = [_book(0x100, 0), _book(0x200, 8)]

    def _record(record_type: str, form_id: int, subs: list[tuple[str, bytes]]):
        return SimpleNamespace(
            header=SimpleNamespace(form_id=form_id, type=record_type),
            subrecords=[SimpleNamespace(type=t, data=d) for t, d in subs],
        )

    # One placed direct Barter book and one container template with 2x Science.
    by_type = {
        "REFR": [_record("REFR", 0x500, [("NAME", struct.pack("<I", 0x100))])],
        "ACHR": [],
        "ACRE": [],
        "CONT": [_record("CONT", 0x600, [("CNTO", struct.pack("<Ii", 0x200, 2))])],
        "NPC_": [],
        "CREA": [],
    }

    def _iter_records(_data: bytes, record_types: tuple[str, ...]):
        for record_type in record_types:
            yield from by_type.get(record_type, [])

    monkeypatch.setattr("fnv_planner.parser.book_stats.iter_records_of_types", _iter_records)
    counts = placed_skill_book_copies_by_actor_value([b"fake"], merged_books)
    assert sum(counts.values()) == 3
