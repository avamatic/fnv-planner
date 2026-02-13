from types import SimpleNamespace

import scripts.dump_items as dump_items


def _weapon(
    form_id: int,
    name: str,
    editor_id: str,
    damage: int = 10,
    value: int = 100,
    weight: float = 1.0,
    stat_effects=None,
    is_playable: bool = True,
    weapon_flags_1: int = 0,
    weapon_flags_2: int = 0,
):
    return SimpleNamespace(
        form_id=form_id,
        name=name,
        editor_id=editor_id,
        damage=damage,
        value=value,
        weight=weight,
        is_playable=is_playable,
        weapon_flags_1=weapon_flags_1,
        weapon_flags_2=weapon_flags_2,
        is_non_playable_flagged=bool(weapon_flags_1 & 0x80),
        is_embedded_weapon=bool(weapon_flags_1 & 0x20),
        stat_effects=list(stat_effects or []),
    )


def _effect(actor_value_name: str, magnitude: float, duration: float, is_hostile: bool):
    return SimpleNamespace(
        actor_value_name=actor_value_name,
        magnitude=magnitude,
        duration=duration,
        is_hostile=is_hostile,
    )


def test_is_player_facing_weapon_filters_companion_and_npc_helpers():
    player = _weapon(1, "Grenade Launcher", "WeapNVGrenadeLauncher")
    companion = _weapon(2, "Assault Carbine", "WeapNVAssaultCarbineLily")
    npc_robot = _weapon(3, "Grenade Launcher", "WeapNVSecuritronLauncher")

    assert dump_items._is_player_facing_weapon(player) is True
    assert dump_items._is_player_facing_weapon(companion) is False
    assert dump_items._is_player_facing_weapon(npc_robot) is False


def test_build_weapon_disambiguation_labels_prefers_human_label_then_editor_id():
    lily = _weapon(10, "Assault Carbine", "WeapNVAssaultCarbineLily")
    base = _weapon(11, "Assault Carbine", "WeapNVAssaultCarbine")

    labels = dump_items._build_weapon_disambiguation_labels([lily, base])

    assert labels[10] == "Lily"
    assert labels[11] == "WeapNVAssaultCarbine"


def test_build_weapon_disambiguation_labels_resolves_colliding_labels():
    npc_a = _weapon(20, "Sawed-Off Shotgun", "WeapShotgunSawedOffNPC")
    npc_b = _weapon(21, "Sawed-Off Shotgun", "WeapShotgunRiotNPC")

    labels = dump_items._build_weapon_disambiguation_labels([npc_a, npc_b])

    assert labels[20] == "WeapShotgunSawedOffNPC"
    assert labels[21] == "WeapShotgunRiotNPC"


def test_build_weapon_disambiguation_labels_ignores_unique_names():
    a = _weapon(30, "Service Rifle", "WeapNVServiceRifle")
    b = _weapon(31, "Riot Shotgun", "WeapNVRiotShotgun")

    labels = dump_items._build_weapon_disambiguation_labels([a, b])

    assert labels == {}


def test_dedupe_key_includes_effect_context():
    hostile = _effect("Health", -2, 5, True)
    friendly = _effect("Health", +2, 5, False)
    w1 = _weapon(40, "Test Blade", "WeapA", stat_effects=[hostile])
    w2 = _weapon(41, "Test Blade", "WeapB", stat_effects=[friendly])

    deduped = dump_items._dedupe_weapons_for_display([w1, w2])

    assert len(deduped) == 2


def test_format_effects_timed_player_effect_is_not_per_second():
    eff = _effect("Intelligence", 1, 240, False)

    rendered = dump_items.format_effects([eff])

    assert rendered == "[+1 Intelligence*240s]{Player}"


def test_format_effects_timed_hostile_effect_is_per_second():
    eff = _effect("Health", -2, 10, True)

    rendered = dump_items.format_effects([eff])

    assert rendered == "[-2 Health/s*10s]{Enemy}"


def test_weapon_display_name_uses_disambiguation_over_variant_suffix():
    w = _weapon(99, "Assault Carbine", "WeapNVAssaultCarbineLily")

    display = dump_items._weapon_display_name(w, {99: "Lily"})

    assert display == "Assault Carbine [Lily]"


def test_weapon_classification_exposes_record_flag_and_player_facing():
    fire_gecko = _weapon(100, "Fire Gecko Breath", "WeapNVFireGeckoFlame", weapon_flags_1=0xA0)
    player = _weapon(101, "Grenade Launcher", "WeapNVGrenadeLauncher")

    c1 = dump_items._weapon_classification(fire_gecko)
    c2 = dump_items._weapon_classification(player)

    assert c1["record_flag_playable"] is True
    assert c1["is_player_facing"] is False
    assert c2["record_flag_playable"] is True
    assert c2["is_player_facing"] is True


def test_non_playable_or_embedded_flags_force_non_player_facing():
    non_playable = _weapon(102, "Mob Breath", "WeapMobBreath", weapon_flags_1=0x80)
    embedded = _weapon(103, "Embedded Claw", "WeapEmbeddedClaw", weapon_flags_1=0x20)

    assert dump_items._is_player_facing_weapon(non_playable) is False
    assert dump_items._is_player_facing_weapon(embedded) is False
