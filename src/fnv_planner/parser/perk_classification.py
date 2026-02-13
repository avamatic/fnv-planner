"""Perk category classification helpers.

Categories are intentionally data-driven and deterministic:
  - trait: PERK flag
  - challenge: linked CHAL reward or challenge-family editor ID
  - special: visible, non-selectable, non-trait, non-challenge perks
  - internal: hidden non-selectable perks
  - normal: selectable, non-trait, non-challenge perks
"""

from dataclasses import dataclass

from fnv_planner.models.perk import Perk
from fnv_planner.models.records import Record
from fnv_planner.parser.record_reader import read_grup


@dataclass(frozen=True)
class PerkCategory:
    name: str
    reason: str


def challenge_names_from_plugin(data: bytes) -> set[str]:
    try:
        records = read_grup(data, "CHAL")
    except ValueError as exc:
        if "GRUP 'CHAL' not found in plugin" in str(exc):
            return set()
        raise
    names: set[str] = set()
    for record in records:
        full_name = ""
        for sub in record.subrecords:
            if sub.type == "FULL":
                full_name = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")
                break
        if full_name:
            names.add(full_name)
    return names


def detect_challenge_perk_ids(plugin_datas: list[bytes], perks: list[Perk]) -> set[int]:
    chal_names: set[str] = set()
    for data in plugin_datas:
        chal_names |= challenge_names_from_plugin(data)

    ids: set[int] = set()
    for perk in perks:
        # Primary signal: challenge reward names from CHAL records.
        if perk.name in chal_names:
            ids.add(perk.form_id)
            continue
        # Secondary signal: challenge-family PERK editor IDs.
        if "challenge" in perk.editor_id.lower():
            ids.add(perk.form_id)
    return ids


def classify_perk(perk: Perk, challenge_perk_ids: set[int]) -> PerkCategory:
    if perk.is_trait:
        return PerkCategory("trait", "PERK is_trait flag")
    if perk.form_id in challenge_perk_ids:
        return PerkCategory("challenge", "CHAL-linked or challenge-family PERK")
    if perk.is_hidden:
        return PerkCategory("internal", "hidden non-selectable PERK")
    if not perk.is_playable:
        return PerkCategory("special", "visible non-selectable PERK")
    return PerkCategory("normal", "selectable level-up PERK")
