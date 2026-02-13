# Mechanics Source Matrix

This matrix tracks where gameplay mechanics are sourced from in this project.
The goal is to keep mechanics data-driven and avoid silent drift.

## Data-Driven (Parsed)

| Mechanic | Source | Code Path |
|---|---|---|
| Carry weight formula constants | GMST (`fAVDCarryWeightsBase`, `fAVDCarryWeightMult`) | `src/fnv_planner/models/derived_stats.py` |
| Action points formula constants | GMST (`fAVDActionPointsBase`, `fAVDActionPointsMult`) | `src/fnv_planner/models/derived_stats.py` |
| Hit points formula constants (except base 100) | GMST (`fAVDHealthEnduranceMult`, `fAVDHealthLevelMult`) | `src/fnv_planner/models/derived_stats.py` |
| Crit chance formula constants | GMST (`fAVDCritLuckBase`, `fAVDCritLuckMult`) | `src/fnv_planner/models/derived_stats.py` |
| Melee / unarmed constants | GMST (`fAVDMeleeDamageStrengthMult`, `fAVDUnarmedDamageBase`, `fAVDUnarmedDamageMult`) | `src/fnv_planner/models/derived_stats.py` |
| Initial skill base per skill | GMST (`fAVDSkill*Base`) | `src/fnv_planner/models/derived_stats.py` |
| Initial skill multipliers | GMST (`fAVDSkillPrimaryBonusMult`, `fAVDSkillLuckBonusMult`) | `src/fnv_planner/models/derived_stats.py` |
| Tag skill bonus | GMST (`fAVDTagSkillBonus`) | `src/fnv_planner/models/derived_stats.py` |
| Skill points per level base | GMST (`iLevelUpSkillPointsBase`) | `src/fnv_planner/models/derived_stats.py` |
| Level cap | GMST (`iMaxCharacterLevel`) + plugin load-order merge | `src/fnv_planner/models/derived_stats.py`, `src/fnv_planner/parser/plugin_merge.py` |
| Skill book base points | GMST (`fBookPerkBonus`) | `src/fnv_planner/models/game_settings.py`, `src/fnv_planner/optimizer/planner.py` |
| Comprehension-like skill book bonus | PERK entry-point effect (`function_id == 11`, EPFD float) | `src/fnv_planner/parser/perk_parser.py`, `src/fnv_planner/optimizer/planner.py` |
| AV labels/metadata | AVIF (`EDID/FULL/DESC/ANAM/ICON`) | `src/fnv_planner/parser/avif_parser.py` |

## Engine-Defined (Still Hardcoded)

| Mechanic | Current Behavior | Why Still Hardcoded |
|---|---|---|
| Poison resistance | `(END - 1) * 5` | No formula coefficient found in parsed GMST/AVIF records. |
| Radiation resistance | `(END - 1) * 2` | No formula coefficient found in parsed GMST/AVIF records. |
| Companion nerve | `CHA * 5` | No formula coefficient found in parsed GMST/AVIF records. |
| HP base constant | `100` additive base | Not represented as a parsed GMST in current pipeline. |

## Audit Notes

- AVIF parsing is intentionally metadata-oriented. In current FalloutNV.esm data,
  AVIF subrecords are descriptive (`EDID`, `FULL`, `DESC`, `ANAM`, `ICON`) and
  do not expose derived-stat formula coefficients.
- If future work finds authoritative formula data in non-GMST records, extend
  the parser and move the corresponding row from "Engine-Defined" to "Data-Driven".

## Mechanics Key Coverage

<!-- MECHANICS_MATRIX_KEYS_START -->
# Keep this list in sync with scripts.audit_mechanics_sources.MECHANICS_ROWS
action_points.base
action_points.mult
carry_weight.base
carry_weight.mult
companion_nerve.mult
crit.base
crit.mult
health.base
health.endurance_mult
health.level_mult
melee.mult
poison_resistance.mult
rad_resistance.mult
skill.luck_mult
skill.primary_mult
skill.tag_bonus
skill_book.base_points
skill_points_per_level.base
unarmed.base
unarmed.mult
<!-- MECHANICS_MATRIX_KEYS_END -->

## Hardcoded Literal Allowlist

<!-- HARD_CODED_LITERALS_ALLOWLIST_START -->
# method:literal
companion_nerve:5.0
poison_resistance:1
poison_resistance:5.0
rad_resistance:1
rad_resistance:2.0
<!-- HARD_CODED_LITERALS_ALLOWLIST_END -->
