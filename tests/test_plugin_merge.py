from fnv_planner.models.game_settings import GameSettings
from fnv_planner.parser.plugin_merge import (
    VANILLA_PLUGIN_ORDER,
    default_vanilla_plugins,
    parse_dict_merged,
    parse_records_merged,
)


class _Row:
    def __init__(self, form_id: int, value: int):
        self.form_id = form_id
        self.value = value


def test_parse_records_merged_last_wins():
    p1 = b"plugin1"
    p2 = b"plugin2"

    def parser(data: bytes):
        if data == p1:
            return [_Row(1, 10), _Row(2, 20)]
        return [_Row(2, 99), _Row(3, 30)]

    rows = parse_records_merged([p1, p2], parser)
    by_id = {r.form_id: r for r in rows}

    assert by_id[1].value == 10
    assert by_id[2].value == 99
    assert by_id[3].value == 30


def test_parse_dict_merged_last_wins():
    p1 = b"plugin1"
    p2 = b"plugin2"

    def parser(data: bytes):
        if data == p1:
            return {"a": 1, "b": 2}
        return {"b": 9, "c": 3}

    merged = parse_dict_merged([p1, p2], parser)
    assert merged == {"a": 1, "b": 9, "c": 3}


def test_game_settings_from_plugins_uses_merge(monkeypatch):
    p1 = b"plugin1"
    p2 = b"plugin2"

    from fnv_planner.parser import gmst_parser
    monkeypatch.setattr(
        gmst_parser,
        "parse_all_gmsts",
        lambda data: {"iMaxCharacterLevel": 35} if data == p1 else {"iMaxCharacterLevel": 60},
    )
    gs = GameSettings.from_plugins([p1, p2])
    assert gs.get_int("iMaxCharacterLevel", 0) == 60


def test_default_vanilla_plugins_returns_existing_and_missing(tmp_path):
    data_dir = tmp_path / "Data"
    data_dir.mkdir()
    (data_dir / "FalloutNV.esm").write_bytes(b"x")
    (data_dir / "HonestHearts.esm").write_bytes(b"x")

    existing, missing = default_vanilla_plugins(data_dir / "FalloutNV.esm")

    assert [p.name for p in existing] == ["FalloutNV.esm", "HonestHearts.esm"]
    assert set(p.name for p in missing) == set(VANILLA_PLUGIN_ORDER) - {"FalloutNV.esm", "HonestHearts.esm"}


def test_default_vanilla_plugins_fallback_to_primary(tmp_path):
    custom = tmp_path / "MyBase.esm"
    custom.write_bytes(b"x")

    existing, missing = default_vanilla_plugins(custom)

    assert existing == [custom]
    assert missing == []
