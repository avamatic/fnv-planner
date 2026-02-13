from pathlib import Path

import pytest

from fnv_planner.models.constants import ActorValue
from fnv_planner.optimizer.planner import _infer_perk_skill_effects
from fnv_planner.parser.perk_parser import parse_all_perks
from fnv_planner.parser.plugin_merge import (
    default_vanilla_plugins,
    load_plugin_bytes,
    parse_records_merged,
)
from fnv_planner.parser.spell_parser import (
    linked_spell_names_by_form,
    linked_spell_stat_bonuses_by_form,
)


ESM_PATH = Path(
    "/home/am/.local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm"
)


def _has_lonesome_road() -> bool:
    if not ESM_PATH.exists():
        return False
    existing, _missing = default_vanilla_plugins(ESM_PATH)
    return any(p.name.lower() == "lonesomeroad.esm" for p in existing)


pytestmark = pytest.mark.skipif(
    not _has_lonesome_road(), reason="Vanilla+DLC plugin stack not available"
)


def test_broad_daylight_conditional_sneak_bonus_not_counted_for_planning():
    existing, _missing = default_vanilla_plugins(ESM_PATH)
    plugin_datas = load_plugin_bytes(existing)

    perks = parse_records_merged(plugin_datas, parse_all_perks, missing_group_ok=True)
    perk_by_edid = {p.editor_id: p for p in perks}
    broad_daylight = perk_by_edid["NVDLC04BroadDaylightPerk"]

    strict_names = linked_spell_names_by_form(plugin_datas)
    strict_bonuses = linked_spell_stat_bonuses_by_form(plugin_datas)
    strict_effects = _infer_perk_skill_effects(
        broad_daylight,
        linked_spell_names_by_form=strict_names,
        linked_spell_stat_bonuses_by_form=strict_bonuses,
    )
    assert int(ActorValue.SNEAK) not in strict_effects.per_skill_bonus

    all_names = linked_spell_names_by_form(plugin_datas, include_conditional=True)
    all_bonuses = linked_spell_stat_bonuses_by_form(plugin_datas, include_conditional=True)
    permissive_effects = _infer_perk_skill_effects(
        broad_daylight,
        linked_spell_names_by_form=all_names,
        linked_spell_stat_bonuses_by_form=all_bonuses,
    )
    assert permissive_effects.per_skill_bonus.get(int(ActorValue.SNEAK), 0) > 0
