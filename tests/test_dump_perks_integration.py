from pathlib import Path

import pytest

import scripts.dump_perks as dump_perks
from fnv_planner.parser.perk_parser import parse_all_perks
from fnv_planner.parser.plugin_merge import (
    VANILLA_PLUGIN_ORDER,
    load_plugin_bytes,
    parse_records_merged,
    resolve_plugins_for_cli,
)


DEFAULT_ESM = Path(
    "/home/am/.local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm"
)


def _all_vanilla_plugins_present() -> bool:
    data_dir = DEFAULT_ESM.parent
    return all((data_dir / name).exists() for name in VANILLA_PLUGIN_ORDER)


pytestmark = pytest.mark.skipif(
    not _all_vanilla_plugins_present(),
    reason="Full vanilla+DLC plugin stack not found",
)


@pytest.fixture(scope="module")
def merged_perks():
    paths, _, _ = resolve_plugins_for_cli(None, DEFAULT_ESM)
    plugin_datas = load_plugin_bytes(paths)
    perks = parse_records_merged(plugin_datas, parse_all_perks, missing_group_ok=True)
    return perks, plugin_datas


def test_detected_challenge_perk_count_matches_vanilla_stack(merged_perks):
    perks, plugin_datas = merged_perks
    challenge_ids = dump_perks._detect_challenge_perk_ids(plugin_datas, perks)
    assert len(challenge_ids) == 16


def test_set_lasers_for_fun_detected_as_challenge(merged_perks):
    perks, plugin_datas = merged_perks
    challenge_ids = dump_perks._detect_challenge_perk_ids(plugin_datas, perks)
    by_edid = {p.editor_id: p for p in perks}
    assert by_edid["SetLasersForFunPerk"].form_id in challenge_ids


def test_playable_only_filter_excludes_set_lasers_by_default(merged_perks):
    perks, plugin_datas = merged_perks
    challenge_ids = dump_perks._detect_challenge_perk_ids(plugin_datas, perks)
    filtered = [
        p for p in perks
        if p.is_playable and not p.is_trait and p.form_id not in challenge_ids
    ]
    names = {p.name for p in filtered}
    assert "Set Lasers for Fun" not in names
