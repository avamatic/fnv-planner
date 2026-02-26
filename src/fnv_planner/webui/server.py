"""Web UI serving utilities with a live planner runtime."""

from __future__ import annotations

import json
import threading
import webbrowser
from dataclasses import dataclass
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from fnv_planner.ui.bootstrap import bootstrap_default_session
from fnv_planner.ui.controllers.build_controller import BuildController
from fnv_planner.ui.controllers.library_controller import LibraryController
from fnv_planner.ui.controllers.progression_controller import ProgressionController
from fnv_planner.webui.export_state import build_webui_state, build_webui_state_from_controllers


REPO_ROOT = Path(__file__).resolve().parents[3]
WEBUI_DIR = REPO_ROOT / "webui"
STATE_PATH = WEBUI_DIR / "state.json"


@dataclass(slots=True)
class ActionResult:
    ok: bool
    message: str | None = None


class WebUiRuntime:
    """Live, mutable planner runtime backing web UI API requests."""

    def __init__(
        self,
        *,
        include_max_skills: bool = True,
        include_max_crit: bool = True,
        include_max_crit_damage: bool = False,
        plugin_paths: list[Path] | None = None,
    ) -> None:
        session, state = bootstrap_default_session(plugin_paths)
        self.session = session
        self.state = state
        self.build = BuildController(
            engine=session.engine,
            ui_model=session.ui_model,
            perks=session.perks,
            challenge_perk_ids=session.challenge_perk_ids,
            skill_books_by_av=session.skill_books_by_av,
            linked_spell_names_by_form=session.linked_spell_names_by_form,
            linked_spell_stat_bonuses_by_form=session.linked_spell_stat_bonuses_by_form,
            state=state,
            av_descriptions_by_av=session.av_descriptions_by_av,
            armors_by_id=session.armors,
            weapons_by_id=session.weapons,
            current_level=1,
        )
        self.progression = ProgressionController(
            engine=session.engine,
            ui_model=session.ui_model,
            perks=session.perks,
            state=state,
            av_descriptions_by_av=session.av_descriptions_by_av,
        )
        self.library = LibraryController(
            engine=session.engine,
            ui_model=session.ui_model,
            armors=session.armors,
            weapons=session.weapons,
            state=state,
        )

        if include_max_skills:
            self.build.add_max_skills_request()
        if include_max_crit:
            self.build.add_max_crit_request()
        if include_max_crit_damage:
            self.build.add_max_crit_damage_request()

        self._lock = threading.RLock()

    def snapshot(self) -> dict:
        with self._lock:
            return build_webui_state_from_controllers(
                session=self.session,
                state=self.state,
                build=self.build,
                progression=self.progression,
                library=self.library,
            )

    def apply(self, path: str, payload: dict) -> ActionResult:
        with self._lock:
            if path == "/api/requests/actor-value":
                return self._action_actor_value(payload)
            if path == "/api/requests/crit-damage":
                return self._action_crit_damage(payload)
            if path == "/api/requests/perk-toggle":
                return self._action_perk_toggle(payload)
            if path == "/api/requests/traits":
                return self._action_traits(payload)
            if path == "/api/requests/tagged-skills":
                return self._action_tagged_skills(payload)
            if path == "/api/requests/meta":
                return self._action_meta(payload)
            if path == "/api/requests/remove":
                return self._action_remove_request(payload)
            if path == "/api/requests/move":
                return self._action_move_request(payload)
            if path == "/api/equipment/equip":
                return self._action_equip(payload)
            if path == "/api/equipment/clear":
                return self._action_clear_slot(payload)
            if path == "/api/replan":
                self.build.refresh()
                return ActionResult(ok=True)
            return ActionResult(ok=False, message=f"Unknown API endpoint: {path}")

    def _action_actor_value(self, payload: dict) -> ActionResult:
        actor_value = int(payload.get("actor_value", 0))
        value = int(payload.get("value", 0))
        operator = str(payload.get("operator", ">="))
        reason = str(payload.get("reason", ""))
        ok, message = self.build.add_actor_value_request(
            actor_value=actor_value,
            value=value,
            operator=operator,
            reason=reason,
        )
        return ActionResult(ok=ok, message=message)

    def _action_crit_damage(self, payload: dict) -> ActionResult:
        value = int(payload.get("value", 0))
        operator = str(payload.get("operator", ">="))
        reason = str(payload.get("reason", ""))
        ok, message = self.build.add_crit_damage_potential_request(
            value=value,
            operator=operator,
            reason=reason,
        )
        return ActionResult(ok=ok, message=message)

    def _action_perk_toggle(self, payload: dict) -> ActionResult:
        perk_id = int(payload.get("perk_id", 0))
        selected = bool(payload.get("selected", False))
        self.build.set_desired_perk_selected(perk_id, selected)
        return ActionResult(ok=True)

    def _action_traits(self, payload: dict) -> ActionResult:
        trait_ids = {int(v) for v in payload.get("trait_ids", [])}
        ok, message = self.build.set_trait_requests(trait_ids)
        return ActionResult(ok=ok, message=message)

    def _action_tagged_skills(self, payload: dict) -> ActionResult:
        skill_avs = {int(v) for v in payload.get("skill_avs", [])}
        ok, message = self.build.set_tagged_skill_requests(skill_avs)
        return ActionResult(ok=ok, message=message)

    def _action_meta(self, payload: dict) -> ActionResult:
        kind = str(payload.get("kind", ""))
        enabled = bool(payload.get("enabled", False))
        try:
            self.build.set_meta_request_enabled(kind, enabled)
        except ValueError as exc:
            return ActionResult(ok=False, message=str(exc))
        return ActionResult(ok=True)

    def _action_remove_request(self, payload: dict) -> ActionResult:
        self.build.remove_priority_request(int(payload.get("index", -1)))
        return ActionResult(ok=True)

    def _action_move_request(self, payload: dict) -> ActionResult:
        index = int(payload.get("index", -1))
        delta = int(payload.get("delta", 0))
        self.build.move_priority_request(index, delta)
        return ActionResult(ok=True)

    def _action_equip(self, payload: dict) -> ActionResult:
        form_id = int(payload.get("form_id", 0))
        item = self.library.get_item(form_id)
        if item is None:
            return ActionResult(ok=False, message=f"Unknown gear item: {form_id}")
        self.session.engine.set_equipment(int(item.equipment_slot), int(item.form_id))
        self.build.refresh()
        self.progression.refresh()
        self.library.refresh()
        return ActionResult(ok=True)

    def _action_clear_slot(self, payload: dict) -> ActionResult:
        slot = int(payload.get("slot", -1))
        if slot < 0:
            return ActionResult(ok=False, message="slot is required")
        self.library.clear_slot(slot)
        self.build.refresh()
        self.progression.refresh()
        return ActionResult(ok=True)


class WebUiRequestHandler(SimpleHTTPRequestHandler):
    """Static-file handler with JSON API routes."""

    def __init__(self, *args, runtime: WebUiRuntime, directory: str, **kwargs):
        self._runtime = runtime
        super().__init__(*args, directory=directory, **kwargs)

    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path in {"/api/state", "/state.json"}:
            self._send_json(self._runtime.snapshot())
            return
        super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            self._send_json({"ok": False, "message": "Unknown endpoint"}, status=HTTPStatus.NOT_FOUND)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0

        raw = self.rfile.read(length) if length > 0 else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") if raw else "{}")
        except json.JSONDecodeError:
            self._send_json({"ok": False, "message": "Invalid JSON body"}, status=HTTPStatus.BAD_REQUEST)
            return

        if not isinstance(payload, dict):
            self._send_json({"ok": False, "message": "JSON body must be an object"}, status=HTTPStatus.BAD_REQUEST)
            return

        result = self._runtime.apply(path, payload)
        response = {
            "ok": bool(result.ok),
            "message": result.message,
            "state": self._runtime.snapshot(),
        }
        status = HTTPStatus.OK if result.ok else HTTPStatus.BAD_REQUEST
        self._send_json(response, status=status)


def write_state(
    path: Path = STATE_PATH,
    *,
    runtime: WebUiRuntime | None = None,
    plugin_paths: list[Path] | None = None,
) -> dict:
    """Write a one-shot JSON snapshot for offline inspection."""
    path.parent.mkdir(parents=True, exist_ok=True)
    state = runtime.snapshot() if runtime is not None else build_webui_state(plugin_paths=plugin_paths)
    path.write_text(json.dumps(state, indent=2))
    return state


def make_server(
    host: str,
    port: int,
    directory: Path = WEBUI_DIR,
    *,
    runtime: WebUiRuntime | None = None,
) -> ThreadingHTTPServer:
    active_runtime = runtime or WebUiRuntime()
    handler = partial(
        WebUiRequestHandler,
        directory=str(directory),
        runtime=active_runtime,
    )
    server = ThreadingHTTPServer((host, port), handler)
    server.webui_runtime = active_runtime  # type: ignore[attr-defined]
    return server


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 4173,
    open_browser: bool = True,
    plugin_paths: list[Path] | None = None,
) -> None:
    runtime = WebUiRuntime(plugin_paths=plugin_paths)
    state = write_state(STATE_PATH, runtime=runtime)
    server = make_server(host, port, WEBUI_DIR, runtime=runtime)
    url = f"http://{host}:{port}/index.html"
    print(f"State written: {STATE_PATH}")
    print(f"Target level: {state['app']['target_level']} | plugin mode: {state['app']['plugin_mode']}")
    print(f"Serving {WEBUI_DIR} at {url}")

    if open_browser:
        webbrowser.open(url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
