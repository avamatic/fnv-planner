"""Helpers for deriving skill-book availability from parsed BOOK records."""

from __future__ import annotations

import struct
from dataclasses import dataclass

from fnv_planner.models.constants import ActorValue
from fnv_planner.models.item import Book
from fnv_planner.parser.record_reader import iter_records_of_types


@dataclass(slots=True)
class SkillBookSourceBreakdown:
    static_world_by_av: dict[int, int]
    craftable_by_av: dict[int, int]
    random_pool_by_av: dict[int, int]

    @property
    def static_total(self) -> int:
        return sum(self.static_world_by_av.values())

    @property
    def craftable_total(self) -> int:
        return sum(self.craftable_by_av.values())

    @property
    def random_pool_total(self) -> int:
        return sum(self.random_pool_by_av.values())


_OWB_RECIPE_SKILL_SUFFIX_TO_AV: dict[str, int] = {
    "Barter": int(ActorValue.BARTER),
    "EnergyWeap": int(ActorValue.ENERGY_WEAPONS),
    "Explosives": int(ActorValue.EXPLOSIVES),
    "Guns": int(ActorValue.GUNS),
    "Lockpicking": int(ActorValue.LOCKPICK),
    "Medicine": int(ActorValue.MEDICINE),
    "MeleeWeap": int(ActorValue.MELEE_WEAPONS),
    "Repair": int(ActorValue.REPAIR),
    "Science": int(ActorValue.SCIENCE),
    "Sneak": int(ActorValue.SNEAK),
    "Speech": int(ActorValue.SPEECH),
    "Survival": int(ActorValue.SURVIVAL),
    "Unarmed": int(ActorValue.UNARMED),
}


def skill_books_by_actor_value(books: list[Book]) -> dict[int, int]:
    """Count skill books by target skill actor value.

    Input is typically already load-order merged by form_id.
    """
    counts: dict[int, int] = {}
    for book in books:
        av = book.skill_actor_value
        if av is None:
            continue
        counts[int(av)] = counts.get(int(av), 0) + 1
    return counts


def total_skill_books(books: list[Book]) -> int:
    """Total number of parsed skill-book records."""
    return sum(skill_books_by_actor_value(books).values())


def skill_book_source_breakdown(
    plugin_datas: list[bytes],
    merged_books: list[Book],
) -> SkillBookSourceBreakdown:
    """Classify skill-book supply into static/craftable/random buckets."""
    book_to_av: dict[int, int] = {}
    for book in merged_books:
        av = book.skill_actor_value
        if av is None:
            continue
        book_to_av[int(book.form_id)] = int(av)

    static_world: dict[int, int] = {}
    random_pool: dict[int, int] = {}
    craftable: dict[int, int] = {}

    wanted = ("REFR", "ACHR", "ACRE", "LVLI", "MISC")
    for data in plugin_datas:
        for rec in iter_records_of_types(data, wanted):
            record_type = rec.header.type
            if record_type in {"REFR", "ACHR", "ACRE"}:
                for sub in rec.subrecords:
                    if sub.type != "NAME" or len(sub.data) < 4:
                        continue
                    base_form = struct.unpack_from("<I", sub.data, 0)[0]
                    av = book_to_av.get(int(base_form))
                    if av is not None:
                        static_world[av] = static_world.get(av, 0) + 1
                    break
                continue

            if record_type == "LVLI":
                for sub in rec.subrecords:
                    # LVLO: level(u16) + unknown(u16) + form(u32) + count(u16) + chance_none(u8) + unknown(u8)
                    if sub.type != "LVLO" or len(sub.data) < 12:
                        continue
                    entry_form = struct.unpack_from("<I", sub.data, 4)[0]
                    av = book_to_av.get(int(entry_form))
                    if av is not None:
                        # Count entries, not expected spawned copies.
                        random_pool[av] = random_pool.get(av, 0) + 1
                continue

            if record_type == "MISC":
                edid = ""
                for sub in rec.subrecords:
                    if sub.type != "EDID":
                        continue
                    edid = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
                    break
                prefix = "NVDLC03RecipeSkillBook"
                suffix = "ITEM"
                if not edid.startswith(prefix) or not edid.endswith(suffix):
                    continue
                skill_suffix = edid[len(prefix):-len(suffix)]
                av = _OWB_RECIPE_SKILL_SUFFIX_TO_AV.get(skill_suffix)
                if av is not None:
                    craftable[av] = craftable.get(av, 0) + 1

    return SkillBookSourceBreakdown(
        static_world_by_av=static_world,
        craftable_by_av=craftable,
        random_pool_by_av=random_pool,
    )


def placed_skill_book_copies_by_actor_value(
    plugin_datas: list[bytes],
    merged_books: list[Book],
) -> dict[int, int]:
    """Count detected skill-book copies from plugin content.

    Includes:
    - placed world references that directly point to BOOK forms
    - inventory-template copies embedded in CONT/NPC_/CREA records

    This intentionally goes beyond unique BOOK templates so totals better match
    practical in-game availability.
    """
    # Backward-compatible aggregate used by planner/UI today:
    # static placed copies + inventory-template copies.
    book_to_av: dict[int, int] = {
        int(book.form_id): int(book.skill_actor_value)
        for book in merged_books
        if book.skill_actor_value is not None
    }
    static_counts = skill_book_source_breakdown(plugin_datas, merged_books).static_world_by_av

    inventory_counts: dict[int, int] = {}
    for data in plugin_datas:
        for rec in iter_records_of_types(data, ("CONT", "NPC_", "CREA")):
            for sub in rec.subrecords:
                if sub.type != "CNTO" or len(sub.data) < 8:
                    continue
                item_form = struct.unpack_from("<I", sub.data, 0)[0]
                count = struct.unpack_from("<i", sub.data, 4)[0]
                if count <= 0:
                    continue
                av = book_to_av.get(int(item_form))
                if av is None:
                    continue
                inventory_counts[av] = inventory_counts.get(av, 0) + int(count)

    counts = dict(static_counts)
    for av, count in inventory_counts.items():
        counts[av] = counts.get(av, 0) + count
    return counts
