"""Audit mechanics formula sources and hunt non-GMST candidates.

Usage:
  python -m scripts.audit_mechanics_sources
  python -m scripts.audit_mechanics_sources --hunt-non-gmst
  python -m scripts.audit_mechanics_sources --esm /path/to/FalloutNV.esm --hunt-non-gmst
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

from fnv_planner.models.game_settings import GameSettings
from fnv_planner.parser.plugin_merge import load_plugin_bytes, resolve_plugins_for_cli
from fnv_planner.parser.record_reader import iter_records_of_types


DEFAULT_ESM = Path(
    "/home/am/.local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm"
)

MECHANICS_ROWS: list[tuple[str, str, str, float | int]] = [
    ("carry_weight.base", "GMST", "fAVDCarryWeightsBase", 150.0),
    ("carry_weight.mult", "GMST", "fAVDCarryWeightMult", 10.0),
    ("action_points.base", "GMST", "fAVDActionPointsBase", 65.0),
    ("action_points.mult", "GMST", "fAVDActionPointsMult", 3.0),
    ("health.endurance_mult", "GMST", "fAVDHealthEnduranceMult", 20.0),
    ("health.level_mult", "GMST", "fAVDHealthLevelMult", 5.0),
    ("health.base", "ENGINE_DEFINED", "(constant)", 100),
    ("crit.base", "GMST", "fAVDCritLuckBase", 0.0),
    ("crit.mult", "GMST", "fAVDCritLuckMult", 1.0),
    ("melee.mult", "GMST", "fAVDMeleeDamageStrengthMult", 0.5),
    ("unarmed.base", "GMST", "fAVDUnarmedDamageBase", 0.5),
    ("unarmed.mult", "GMST", "fAVDUnarmedDamageMult", 0.05),
    ("skill.primary_mult", "GMST", "fAVDSkillPrimaryBonusMult", 2.0),
    ("skill.luck_mult", "GMST", "fAVDSkillLuckBonusMult", 0.5),
    ("skill.tag_bonus", "GMST", "fAVDTagSkillBonus", 15.0),
    ("skill_points_per_level.base", "GMST", "iLevelUpSkillPointsBase", 11),
    ("skill_book.base_points", "GMST", "fBookPerkBonus", 3.0),
    ("poison_resistance.mult", "ENGINE_DEFINED", "(constant)", 5),
    ("rad_resistance.mult", "ENGINE_DEFINED", "(constant)", 2),
    ("companion_nerve.mult", "ENGINE_DEFINED", "(constant)", 5),
]


def _decoded_text(data: bytes) -> str:
    return data.rstrip(b"\x00").decode("utf-8", errors="replace")


def _gmst_value(gmst: GameSettings, key: str, fallback: float | int) -> str:
    if key.startswith("i"):
        return str(gmst.get_int(key, int(fallback)))
    return f"{gmst.get_float(key, float(fallback)):.6g}"


def _print_matrix(gmst: GameSettings) -> None:
    print("== Mechanics Source Audit ==")
    for mechanic, source, key, fallback in MECHANICS_ROWS:
        value = _gmst_value(gmst, key, fallback) if source == "GMST" else str(fallback)
        print(f"{mechanic:<30} source={source:<14} key={key:<28} value={value}")

    print("\n-- Per-skill base GMST keys --")
    for key in (
        "fAVDSkillBarterBase",
        "fAVDSkillBigGunsBase",
        "fAVDSkillEnergyWeaponsBase",
        "fAVDSkillExplosivesBase",
        "fAVDSkillLockpickBase",
        "fAVDSkillMedicineBase",
        "fAVDSkillMeleeWeaponsBase",
        "fAVDSkillRepairBase",
        "fAVDSkillScienceBase",
        "fAVDSkillSmallGunsBase",
        "fAVDSkillSneakBase",
        "fAVDSkillSpeechBase",
        "fAVDSkillSurvivalBase",
        "fAVDSkillUnarmedBase",
    ):
        print(f"{key:<28} value={_gmst_value(gmst, key, 2.0)}")


def _hunt_non_gmst(plugin_datas: list[bytes]) -> None:
    print("\n== Non-GMST Candidate Hunt ==")
    wanted_types = ("AVIF", "GLOB", "MGEF", "PERK", "RACE")
    keywords = ("poison", "radiat", "rad", "companion", "nerve", "health")
    hits: list[str] = []

    for data in plugin_datas:
        for record in iter_records_of_types(data, wanted_types):
            text_parts: list[str] = []
            fltv: float | None = None
            for sub in record.subrecords:
                if sub.type in {"EDID", "FULL", "DESC", "ANAM"}:
                    text_parts.append(_decoded_text(sub.data))
                elif sub.type == "FLTV" and len(sub.data) >= 4:
                    fltv = struct.unpack_from("<f", sub.data, 0)[0]
            merged = " | ".join(text_parts).lower()
            if not any(k in merged for k in keywords):
                continue
            text = " | ".join(text_parts) if text_parts else "(no text subrecords)"
            extra = f" | FLTV={fltv:.6g}" if fltv is not None else ""
            hits.append(f"{record.header.type} {record.header.form_id:#010x} {text}{extra}")

    if not hits:
        print("No candidates found.")
        return
    for line in hits[:200]:
        print(line)
    if len(hits) > 200:
        print(f"... ({len(hits) - 200} more)")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit mechanics formula sources")
    parser.add_argument(
        "--esm",
        type=Path,
        action="append",
        help="Plugin path; repeat in load order (last wins).",
    )
    parser.add_argument(
        "--hunt-non-gmst",
        action="store_true",
        help="Scan candidate non-GMST records for formula clues.",
    )
    args = parser.parse_args()

    paths, missing, _is_explicit = resolve_plugins_for_cli(args.esm, DEFAULT_ESM)
    if missing:
        print("Warning: some default vanilla plugins are missing and will be skipped:")
        for p in missing:
            print(f"  - {p.name}")
    plugin_datas = load_plugin_bytes(paths) if paths else []
    gmst = GameSettings.from_plugins(plugin_datas) if plugin_datas else GameSettings.defaults()

    _print_matrix(gmst)
    if args.hunt_non_gmst:
        _hunt_non_gmst(plugin_datas)


if __name__ == "__main__":
    main()
