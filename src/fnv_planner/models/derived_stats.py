"""Derived stat calculator driven by GameSettings constants.

Each formula template mirrors the Gamebryo engine's stat calculation.
Constants come from GMST records (via GameSettings); formula structure
is engine-defined and hardcoded here.

References:
  - GECK wiki: https://geckwiki.com/index.php/Actor_Values
  - Fallout wiki derived statistics page
"""

import math
from dataclasses import dataclass, field

from fnv_planner.models.character import Character
from fnv_planner.models.constants import (
    ACTOR_VALUE_NAMES,
    SKILL_GOVERNING_ATTRIBUTE,
    SKILL_INDICES,
    ActorValue,
)
from fnv_planner.models.effect import StatEffect
from fnv_planner.models.game_settings import GameSettings
from fnv_planner.models.item import Armor, Weapon


_SKILL_BASE_GMST_BY_AV: dict[int, str] = {
    int(ActorValue.BARTER): "fAVDSkillBarterBase",
    int(ActorValue.BIG_GUNS): "fAVDSkillBigGunsBase",
    int(ActorValue.ENERGY_WEAPONS): "fAVDSkillEnergyWeaponsBase",
    int(ActorValue.EXPLOSIVES): "fAVDSkillExplosivesBase",
    int(ActorValue.LOCKPICK): "fAVDSkillLockpickBase",
    int(ActorValue.MEDICINE): "fAVDSkillMedicineBase",
    int(ActorValue.MELEE_WEAPONS): "fAVDSkillMeleeWeaponsBase",
    int(ActorValue.REPAIR): "fAVDSkillRepairBase",
    int(ActorValue.SCIENCE): "fAVDSkillScienceBase",
    int(ActorValue.GUNS): "fAVDSkillSmallGunsBase",
    int(ActorValue.SNEAK): "fAVDSkillSneakBase",
    int(ActorValue.SPEECH): "fAVDSkillSpeechBase",
    int(ActorValue.SURVIVAL): "fAVDSkillSurvivalBase",
    int(ActorValue.UNARMED): "fAVDSkillUnarmedBase",
}


class DerivedStats:
    """Computes derived stats from SPECIAL/skills using GMST-driven formulas."""

    def __init__(self, gmst: GameSettings) -> None:
        self._gmst = gmst

    def hit_points(self, endurance: int, level: int) -> int:
        """Base HP = 100 + END * fAVDHealthEnduranceMult + (level-1) * fAVDHealthLevelMult."""
        end_mult = self._gmst.get_float("fAVDHealthEnduranceMult", 20.0)
        lvl_mult = self._gmst.get_float("fAVDHealthLevelMult", 5.0)
        return int(100 + endurance * end_mult + (level - 1) * lvl_mult)

    def action_points(self, agility: int) -> int:
        """AP = fAVDActionPointsBase + AGI * fAVDActionPointsMult."""
        base = self._gmst.get_float("fAVDActionPointsBase", 65.0)
        mult = self._gmst.get_float("fAVDActionPointsMult", 3.0)
        return int(base + agility * mult)

    def carry_weight(self, strength: int) -> float:
        """CW = fAVDCarryWeightsBase + STR * fAVDCarryWeightMult."""
        base = self._gmst.get_float("fAVDCarryWeightsBase", 150.0)
        mult = self._gmst.get_float("fAVDCarryWeightMult", 10.0)
        return base + strength * mult

    def crit_chance(self, luck: int) -> float:
        """Crit% = fAVDCritLuckBase + LCK * fAVDCritLuckMult."""
        base = self._gmst.get_float("fAVDCritLuckBase", 0.0)
        mult = self._gmst.get_float("fAVDCritLuckMult", 1.0)
        return base + luck * mult

    def melee_damage(self, strength: int) -> float:
        """Melee damage bonus = STR * fAVDMeleeDamageStrengthMult."""
        mult = self._gmst.get_float("fAVDMeleeDamageStrengthMult", 0.5)
        return strength * mult

    def unarmed_damage(self, unarmed_skill: int) -> float:
        """Unarmed damage = fAVDUnarmedDamageBase + unarmed_skill * fAVDUnarmedDamageMult."""
        base = self._gmst.get_float("fAVDUnarmedDamageBase", 0.5)
        mult = self._gmst.get_float("fAVDUnarmedDamageMult", 0.05)
        return base + unarmed_skill * mult

    def poison_resistance(self, endurance: int) -> float:
        """Poison resistance = (END - 1) * 5. No known GMST — hardcoded."""
        return (endurance - 1) * 5.0

    def rad_resistance(self, endurance: int) -> float:
        """Radiation resistance = (END - 1) * 2. No known GMST — hardcoded."""
        return (endurance - 1) * 2.0

    def skill_points_per_level(self, intelligence: int) -> int:
        """Skill points per level = iLevelUpSkillPointsBase + floor(INT * 0.5)."""
        base = self._gmst.get_int("iLevelUpSkillPointsBase", 11)
        return base + math.floor(intelligence * 0.5)

    def skill_base(self, skill_av: int) -> float:
        """Base contribution for a skill actor value from GMST."""
        key = _SKILL_BASE_GMST_BY_AV.get(int(skill_av))
        if key is None:
            return 2.0
        return self._gmst.get_float(key, 2.0)

    def initial_skill(self, governing_attr: int, luck: int, skill_av: int | None = None) -> int:
        """Initial skill value from GMST base + SPECIAL/luck multipliers."""
        primary_mult = self._gmst.get_float("fAVDSkillPrimaryBonusMult", 2.0)
        luck_mult = self._gmst.get_float("fAVDSkillLuckBonusMult", 0.5)
        base = self.skill_base(skill_av) if skill_av is not None else 2.0
        return int(base + governing_attr * primary_mult + math.ceil(luck * luck_mult))

    def tag_bonus(self) -> int:
        """Bonus added to tagged skills."""
        return int(self._gmst.get_float("fAVDTagSkillBonus", 15.0))

    def companion_nerve(self, charisma: int) -> float:
        """Companion Nerve bonus = CHA * 5. No known GMST — hardcoded."""
        return charisma * 5.0

    def max_level(self) -> int:
        """Maximum character level from iMaxCharacterLevel."""
        return self._gmst.get_int("iMaxCharacterLevel", 50)


def compute_equipment_bonuses(
    character: Character,
    armors: dict[int, Armor],
    weapons: dict[int, Weapon],
) -> dict[int, float]:
    """Sum StatEffects from all equipped gear.

    Only considers permanent, player-targeted effects (not weapon hostile
    effects or timed consumable effects).

    Returns:
        Dict mapping actor_value index → total magnitude from equipment.
    """
    bonuses: dict[int, float] = {}

    for _slot, form_id in character.equipment.items():
        effects: list[StatEffect] = []

        if form_id in armors:
            effects = armors[form_id].stat_effects
        elif form_id in weapons:
            # Only include non-hostile weapon effects (player buffs)
            effects = [e for e in weapons[form_id].stat_effects if not e.is_hostile]

        for effect in effects:
            # Only permanent effects (duration 0)
            if effect.duration == 0 and not effect.is_hostile:
                bonuses[effect.actor_value] = (
                    bonuses.get(effect.actor_value, 0.0) + effect.magnitude
                )

    return bonuses


@dataclass
class CharacterStats:
    """Complete computed stat snapshot for a character build."""

    # Vitals
    hit_points: int = 0
    action_points: int = 0
    carry_weight: float = 0.0

    # Combat
    crit_chance: float = 0.0
    melee_damage: float = 0.0
    unarmed_damage: float = 0.0

    # Resistances
    poison_resistance: float = 0.0
    rad_resistance: float = 0.0

    # Progression
    skill_points_per_level: int = 0
    max_level: int = 50

    # Companion
    companion_nerve: float = 0.0

    # Effective SPECIAL (base + equipment)
    effective_special: dict[int, int] = field(default_factory=dict)

    # Final skill values (base + tag + points + equipment)
    skills: dict[int, int] = field(default_factory=dict)

    # Equipment bonuses for reference
    equipment_bonuses: dict[int, float] = field(default_factory=dict)


def compute_stats(
    character: Character,
    gmst: GameSettings,
    armors: dict[int, Armor] | None = None,
    weapons: dict[int, Weapon] | None = None,
    *,
    include_big_guns: bool = False,
    big_guns_governing_attribute: int = ActorValue.STRENGTH,
) -> CharacterStats:
    """Compute all derived stats for a character at their current level.

    Ties together SPECIAL, skills, equipment bonuses, and GMST-driven
    formulas into a single CharacterStats snapshot.
    """
    armors = armors or {}
    weapons = weapons or {}

    calc = DerivedStats(gmst)

    # Equipment bonuses
    equip_bonuses = compute_equipment_bonuses(character, armors, weapons)

    # Effective SPECIAL = base + equipment bonuses (clamped 1-10 for base,
    # but equipment can push beyond 10)
    effective_special: dict[int, int] = {}
    for av_idx, base_val in character.special.items():
        bonus = equip_bonuses.get(av_idx, 0.0)
        effective_special[av_idx] = int(base_val + bonus)

    # Shorthand for effective SPECIAL
    strength = effective_special.get(ActorValue.STRENGTH, 5)
    perception = effective_special.get(ActorValue.PERCEPTION, 5)
    endurance = effective_special.get(ActorValue.ENDURANCE, 5)
    charisma = effective_special.get(ActorValue.CHARISMA, 5)
    intelligence = effective_special.get(ActorValue.INTELLIGENCE, 5)
    agility = effective_special.get(ActorValue.AGILITY, 5)
    luck = effective_special.get(ActorValue.LUCK, 5)

    # Compute skills: initial + tag bonus + invested points + equipment
    skills: dict[int, int] = {}
    tag_bonus = calc.tag_bonus()
    governing_attribute = dict(SKILL_GOVERNING_ATTRIBUTE)
    if include_big_guns:
        governing_attribute.setdefault(
            ActorValue.BIG_GUNS, big_guns_governing_attribute
        )

    for skill_av in SKILL_INDICES:
        if skill_av not in governing_attribute:
            continue
        gov_av = governing_attribute[skill_av]
        gov_val = effective_special.get(gov_av, 5)

        base = calc.initial_skill(gov_val, luck, skill_av=skill_av)
        if skill_av in character.tagged_skills:
            base += tag_bonus
        base += character.skill_points_spent.get(skill_av, 0)
        base += int(equip_bonuses.get(skill_av, 0.0))
        skills[skill_av] = base

    # Unarmed damage uses the computed unarmed skill
    unarmed_skill = skills.get(ActorValue.UNARMED, 0)

    return CharacterStats(
        hit_points=calc.hit_points(endurance, character.level),
        action_points=calc.action_points(agility),
        carry_weight=calc.carry_weight(strength),
        crit_chance=calc.crit_chance(luck),
        melee_damage=calc.melee_damage(strength),
        unarmed_damage=calc.unarmed_damage(unarmed_skill),
        poison_resistance=calc.poison_resistance(endurance),
        rad_resistance=calc.rad_resistance(endurance),
        skill_points_per_level=calc.skill_points_per_level(intelligence),
        max_level=calc.max_level(),
        companion_nerve=calc.companion_nerve(charisma),
        effective_special=effective_special,
        skills=skills,
        equipment_bonuses=equip_bonuses,
    )
