"""Game settings (GMST) wrapper with typed accessors.

Provides a thin interface over the raw GMST dict parsed from ESM data.
Every accessor takes a default so the model works without ESM parsing —
vanilla FNV defaults are available via GameSettings.defaults().
"""

from dataclasses import dataclass, field


# Vanilla FNV defaults for all GMST values we use in stat formulas.
_VANILLA_DEFAULTS: dict[str, int | float | str] = {
    # Carry weight: base + STR * mult
    "fAVDCarryWeightsBase": 150.0,
    "fAVDCarryWeightMult": 10.0,
    # Action points: base + AGI * mult
    "fAVDActionPointsBase": 65.0,
    "fAVDActionPointsMult": 3.0,
    # Hit points: END * mult + (level-1) * level_mult (+ base 100 hardcoded)
    "fAVDHealthEnduranceMult": 20.0,
    "fAVDHealthLevelMult": 5.0,
    # Critical hit chance: base + LCK * mult
    "fAVDCritLuckBase": 0.0,
    "fAVDCritLuckMult": 1.0,
    # Melee damage bonus: STR * mult
    "fAVDMeleeDamageStrengthMult": 0.5,
    # Unarmed damage: base + unarmed_skill * mult
    "fAVDUnarmedDamageBase": 0.5,
    "fAVDUnarmedDamageMult": 0.05,
    # Skill formula: governing_attr * primary_mult + LCK * luck_mult + 2
    "fAVDSkillPrimaryBonusMult": 2.0,
    "fAVDSkillLuckBonusMult": 0.5,
    # Tag skill bonus
    "fAVDTagSkillBonus": 15.0,
    # Level cap
    "iMaxCharacterLevel": 50,
    # Skill points per level: base + floor(INT * 0.5)
    "iLevelUpSkillPointsBase": 11,
}


@dataclass
class GameSettings:
    """Typed accessor over parsed GMST values.

    Use from_esm() to load from an ESM file, or defaults() to get
    a vanilla FNV instance without needing the game files.
    """

    _values: dict[str, int | float | str] = field(default_factory=dict)

    def get_float(self, key: str, default: float) -> float:
        """Get a float GMST value, falling back to the provided default."""
        val = self._values.get(key)
        if val is None:
            return default
        return float(val)

    def get_int(self, key: str, default: int) -> int:
        """Get an integer GMST value, falling back to the provided default."""
        val = self._values.get(key)
        if val is None:
            return default
        return int(val)

    @classmethod
    def from_esm(cls, data: bytes) -> "GameSettings":
        """Parse all GMST records from an ESM file."""
        from fnv_planner.parser.gmst_parser import parse_all_gmsts

        return cls(_values=parse_all_gmsts(data))

    @classmethod
    def defaults(cls) -> "GameSettings":
        """Return vanilla FNV defaults — usable without an ESM file."""
        return cls(_values=dict(_VANILLA_DEFAULTS))
