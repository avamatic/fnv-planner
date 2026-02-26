from fnv_planner.webui.export_state import build_webui_state


def test_build_webui_state_shape():
    state = build_webui_state()

    assert "generated_at" in state
    assert "app" in state
    assert "build" in state
    assert "progression" in state
    assert "library" in state

    assert state["app"]["target_level"] >= 1
    assert "game_variant" in state["app"]
    assert "banner_title" in state["app"]
    assert isinstance(state["progression"]["rows"], list)
    assert len(state["progression"]["rows"]) >= 1

    first = state["progression"]["rows"][0]
    assert "stats" in first
    assert "skills" in first
    assert "crit_damage_potential" in first["stats"]
    assert "request_entries" in state["build"]
    assert "gear" in state["library"]
