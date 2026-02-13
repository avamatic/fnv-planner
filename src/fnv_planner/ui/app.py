"""GTK4 + Libadwaita application bootstrap."""

from __future__ import annotations

try:
    import gi
except ImportError as exc:  # pragma: no cover - import guard for missing system deps
    raise SystemExit(
        "PyGObject is required to run the UI. "
        "Install GTK4/Libadwaita bindings, then run `python -m fnv_planner.ui.app`."
    ) from exc

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, Gtk

from fnv_planner.ui.bootstrap import BuildSession, bootstrap_default_session
from fnv_planner.ui.state import UiState
from fnv_planner.ui.views.window import MainWindow


APP_ID = "io.github.fnvplanner.App"


class FnvPlannerApp(Adw.Application):
    """Application object and activation lifecycle."""

    def __init__(self) -> None:
        super().__init__(application_id=APP_ID, flags=Gio.ApplicationFlags.FLAGS_NONE)
        self._session: BuildSession
        self._state: UiState
        self._session, self._state = bootstrap_default_session()

    def do_activate(self) -> None:  # type: ignore[override]
        window = self.props.active_window
        if window is None:
            try:
                window = MainWindow(self, self._state, self._session)
            except RuntimeError as exc:
                raise SystemExit(
                    "Gtk couldn't initialize a display. Run this app from a desktop session."
                ) from exc
        window.present()


def main() -> None:
    """Run the desktop app."""
    init_ok = Gtk.init_check()
    if isinstance(init_ok, tuple):
        init_ok = init_ok[0]
    if not init_ok:
        raise SystemExit(
            "Gtk display initialization failed. Run the UI inside a desktop session."
        )
    app = FnvPlannerApp()
    try:
        app.run([])
    except KeyboardInterrupt:
        # Allow Ctrl+C to terminate cleanly without a traceback.
        return


if __name__ == "__main__":
    main()
