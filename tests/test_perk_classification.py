from types import SimpleNamespace

from fnv_planner.parser.perk_classification import classify_perk


def _perk(
    form_id: int,
    *,
    is_trait: bool = False,
    is_playable: bool = False,
    is_hidden: bool = False,
):
    return SimpleNamespace(
        form_id=form_id,
        is_trait=is_trait,
        is_playable=is_playable,
        is_hidden=is_hidden,
    )


def test_classify_trait():
    p = _perk(1, is_trait=True, is_playable=True)
    assert classify_perk(p, set()).name == "trait"


def test_classify_challenge():
    p = _perk(2, is_playable=True)
    assert classify_perk(p, {2}).name == "challenge"


def test_classify_internal():
    p = _perk(3, is_hidden=True, is_playable=False)
    assert classify_perk(p, set()).name == "internal"


def test_classify_special():
    p = _perk(4, is_hidden=False, is_playable=False)
    assert classify_perk(p, set()).name == "special"


def test_classify_normal():
    p = _perk(5, is_hidden=False, is_playable=True)
    assert classify_perk(p, set()).name == "normal"
