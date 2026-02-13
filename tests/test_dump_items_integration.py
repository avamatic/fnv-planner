from pathlib import Path
import json
import subprocess

import pytest

import scripts.dump_items as dump_items
from fnv_planner.parser.effect_resolver import EffectResolver
from fnv_planner.parser.item_parser import parse_all_weapons


ESM_PATH = Path(
    "/home/am/.local/share/Steam/steamapps/common/Fallout New Vegas/Data/FalloutNV.esm"
)

pytestmark = pytest.mark.skipif(
    not ESM_PATH.exists(), reason="FalloutNV.esm not found"
)


@pytest.fixture(scope="module")
def weapons():
    data = ESM_PATH.read_bytes()
    resolver = EffectResolver.from_esm(data)
    ws = parse_all_weapons(data)
    for w in ws:
        resolver.resolve_weapon(w)
    return ws


def test_player_facing_filter_known_edge_cases(weapons):
    by_edid = {w.editor_id: w for w in weapons}

    assert dump_items._is_player_facing_weapon(by_edid["WeapNVGrenadeLauncher"]) is True
    assert dump_items._is_player_facing_weapon(by_edid["WeapNVSecuritronLauncher"]) is False
    assert dump_items._is_player_facing_weapon(by_edid["WeapNVAssaultCarbineLily"]) is False
    assert dump_items._is_player_facing_weapon(by_edid["WeapNVFireGeckoFlame"]) is False
    assert dump_items._is_player_facing_weapon(by_edid["WeapFlamer"]) is True
    assert dump_items._is_player_facing_weapon(by_edid["WeapMissileLauncher"]) is True
    assert dump_items._is_player_facing_weapon(by_edid["WeapNVMissileLauncherUnique"]) is True
    assert dump_items._is_player_facing_weapon(by_edid["NVWeapMS22Camera"]) is True


def test_plasma_rifle_duplicate_names_are_disambiguated(weapons):
    plasma = [w for w in weapons if w.name == "Plasma Rifle"]
    labels = dump_items._build_weapon_disambiguation_labels(plasma)
    by_edid = {w.editor_id: w for w in plasma}

    assert labels[by_edid["WeapPlasmaRifleAlwaysCrit"].form_id] == "Always-Crit"
    assert labels[by_edid["HVWeapPlasmaRifleWeak"].form_id] == "Weak"
    assert labels[by_edid["WeapPlasmaRifle"].form_id] == "WeapPlasmaRifle"


def test_dedupe_collapses_true_duplicate_rows(weapons):
    # These two are duplicate display rows in the full dump and should collapse.
    pair = [
        w for w in weapons
        if w.editor_id in ("CG02WeapBBGun", "WeapBBGun")
    ]
    assert len(pair) == 2
    deduped = dump_items._dedupe_weapons_for_display(pair)
    assert len(deduped) == 1


def test_dump_items_json_mode_emits_structured_weapon_rows():
    out = subprocess.check_output(
        [
            "python",
            "-m",
            "scripts.dump_items",
            "--weapons",
            "--playable-only",
            "--format",
            "json",
        ],
        text=True,
    )
    payload = json.loads(out)

    assert "categories" in payload
    assert "weapons" in payload["categories"]
    weapons = payload["categories"]["weapons"]["items"]
    assert weapons, "Expected at least one weapon in JSON output"
    sample = weapons[0]
    assert "name" in sample
    assert "display_name" in sample
    assert "editor_id" in sample
    assert "form_id" in sample
    assert "record_flag_playable" in sample
    assert "is_player_facing" in sample


def test_fire_gecko_breath_is_not_player_facing_in_json():
    out = subprocess.check_output(
        [
            "python",
            "-m",
            "scripts.dump_items",
            "--weapons",
            "--format",
            "json",
        ],
        text=True,
    )
    payload = json.loads(out)
    rows = payload["categories"]["weapons"]["items"]
    gecko = next(r for r in rows if r["editor_id"] == "WeapNVFireGeckoFlame")

    assert gecko["record_flag_playable"] is True
    assert gecko["non_playable_flagged"] is True
    assert gecko["is_player_facing"] is False


def test_codac_camera_is_player_facing_in_json():
    out = subprocess.check_output(
        [
            "python",
            "-m",
            "scripts.dump_items",
            "--weapons",
            "--format",
            "json",
        ],
        text=True,
    )
    payload = json.loads(out)
    rows = payload["categories"]["weapons"]["items"]
    codac = next(r for r in rows if r["editor_id"] == "NVWeapMS22Camera")

    assert codac["record_flag_playable"] is True
    assert codac["non_playable_flagged"] is False
    assert codac["embedded_weapon_flagged"] is False
    assert codac["is_player_facing"] is True
