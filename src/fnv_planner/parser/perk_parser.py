"""Parse PERK records into Perk objects with typed requirements.

Key parsing rule:
  - CTDAs *before* the first PRKE subrecord = perk requirements
  - CTDAs *inside* PRKE…PRKF blocks = effect conditions (ignored for now)

CTDA subrecord layout (28 bytes):
  byte  0:    type flags (bits 5-7 = comparison operator, bit 0 = OR flag)
  bytes 1-3:  unused
  bytes 4-7:  comparison value (float32)
  bytes 8-9:  function index (uint16)
  bytes 10-11: padding
  bytes 12-15: param1 (uint32)
  bytes 16-19: param2 (uint32)
  bytes 20-23: run-on type (uint32)
  bytes 24-27: reference (uint32)
"""

import struct

from fnv_planner.models.constants import (
    ACTOR_VALUE_NAMES,
    COMPARISON_SYMBOLS,
    SKILL_INDICES,
    SPECIAL_INDICES,
    ConditionFunction,
)
from fnv_planner.models.perk import (
    LevelRequirement,
    Perk,
    PerkRequirement,
    RawCondition,
    SexRequirement,
    SkillRequirement,
)
from fnv_planner.models.records import Record, Subrecord


def _decode_ctda(sub: Subrecord) -> dict:
    """Decode a CTDA subrecord into its component fields."""
    d = sub.data
    type_byte = d[0]
    comp_value = struct.unpack_from("<f", d, 4)[0]
    func_idx = struct.unpack_from("<H", d, 8)[0]
    param1 = struct.unpack_from("<I", d, 12)[0]
    param2 = struct.unpack_from("<I", d, 16)[0]

    comp_op = (type_byte >> 5) & 0x07
    is_or = bool(type_byte & 0x01)

    return {
        "function": func_idx,
        "operator": comp_op,
        "operator_symbol": COMPARISON_SYMBOLS.get(comp_op, f"?{comp_op}"),
        "value": comp_value,
        "param1": param1,
        "param2": param2,
        "is_or": is_or,
    }


def parse_perk(record: Record) -> Perk:
    """Parse a PERK Record into a Perk dataclass."""
    editor_id = ""
    full_name = ""
    description = ""
    is_trait = False
    min_level = 0
    ranks = 1
    is_playable = False
    is_hidden = False

    skill_reqs: list[SkillRequirement] = []
    perk_reqs: list[PerkRequirement] = []
    sex_req: SexRequirement | None = None
    level_reqs: list[LevelRequirement] = []
    raw_conds: list[RawCondition] = []

    # Track whether we've hit the first PRKE — after that, CTDAs are effect conditions
    seen_prke = False
    # Track whether the next DATA is the perk metadata (5 bytes) or an effect DATA
    seen_perk_data = False

    for sub in record.subrecords:
        if sub.type == "EDID":
            editor_id = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")

        elif sub.type == "FULL":
            full_name = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")

        elif sub.type == "DESC":
            description = sub.data.rstrip(b"\x00").decode("utf-8", errors="replace")

        elif sub.type == "DATA" and not seen_perk_data and len(sub.data) == 5:
            # Perk metadata: trait(1) + min_level(1) + ranks(1) + playable(1) + hidden(1)
            is_trait = bool(sub.data[0])
            min_level = sub.data[1]
            ranks = sub.data[2]
            is_playable = bool(sub.data[3])
            is_hidden = bool(sub.data[4])
            seen_perk_data = True

        elif sub.type == "PRKE":
            seen_prke = True

        elif sub.type == "CTDA" and not seen_prke:
            # This is a perk requirement condition
            ctda = _decode_ctda(sub)
            func = ctda["function"]

            if func == ConditionFunction.GET_PERMANENT_ACTOR_VALUE:
                av = ctda["param1"]
                if av in SPECIAL_INDICES or av in SKILL_INDICES:
                    skill_reqs.append(SkillRequirement(
                        actor_value=av,
                        name=ACTOR_VALUE_NAMES.get(av, f"AV{av}"),
                        operator=ctda["operator_symbol"],
                        value=int(round(ctda["value"])),
                        is_or=ctda["is_or"],
                    ))
                else:
                    raw_conds.append(RawCondition(
                        function=func,
                        operator=ctda["operator_symbol"],
                        value=ctda["value"],
                        param1=ctda["param1"],
                        param2=ctda["param2"],
                        is_or=ctda["is_or"],
                    ))

            elif func == ConditionFunction.HAS_PERK:
                perk_reqs.append(PerkRequirement(
                    perk_form_id=ctda["param1"],
                    rank=int(round(ctda["value"])),
                    is_or=ctda["is_or"],
                ))

            elif func == ConditionFunction.GET_IS_SEX:
                sex_req = SexRequirement(
                    sex=ctda["param1"],
                    is_or=ctda["is_or"],
                )

            elif func == ConditionFunction.GET_LEVEL:
                level_reqs.append(LevelRequirement(
                    operator=ctda["operator_symbol"],
                    value=int(round(ctda["value"])),
                    is_or=ctda["is_or"],
                ))

            else:
                raw_conds.append(RawCondition(
                    function=func,
                    operator=ctda["operator_symbol"],
                    value=ctda["value"],
                    param1=ctda["param1"],
                    param2=ctda["param2"],
                    is_or=ctda["is_or"],
                ))

    return Perk(
        form_id=record.header.form_id,
        editor_id=editor_id,
        name=full_name or editor_id,
        description=description,
        is_trait=is_trait,
        min_level=min_level,
        ranks=ranks,
        is_playable=is_playable,
        is_hidden=is_hidden,
        skill_requirements=skill_reqs,
        perk_requirements=perk_reqs,
        sex_requirement=sex_req,
        level_requirements=level_reqs,
        raw_conditions=raw_conds,
    )


def parse_all_perks(data: bytes) -> list[Perk]:
    """Parse all PERK records from a plugin file."""
    from fnv_planner.parser.record_reader import read_grup
    records = read_grup(data, "PERK")
    return [parse_perk(r) for r in records]
