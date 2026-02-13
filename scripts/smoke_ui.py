"""Headless GTK UI smoke check for fnv-planner.

Runs the real GTK app against a Broadway display server and exits after a
short timeout. This allows quick validation without a manual desktop session.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import time


def _pick_broadway_display() -> str:
    # Keep this deterministic and isolated from default :0/:1 desktop slots.
    return ":94"


def main() -> int:
    parser = argparse.ArgumentParser(description="Headless GTK UI smoke check")
    parser.add_argument(
        "--timeout",
        type=float,
        default=2.0,
        help="Seconds to keep the app running before clean quit.",
    )
    args = parser.parse_args()

    broadwayd = shutil.which("gtk4-broadwayd")
    if broadwayd is None:
        print("gtk4-broadwayd not found; cannot run headless UI smoke.")
        return 1

    display = _pick_broadway_display()
    port = 18094
    proc = subprocess.Popen(
        [broadwayd, display, "--port", str(port), "--address", "127.0.0.1"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(0.2)
    if proc.poll() is not None:
        print("Failed to start gtk4-broadwayd.")
        return 1

    old_env = dict(os.environ)
    os.environ["GDK_BACKEND"] = "broadway"
    os.environ["BROADWAY_DISPLAY"] = display
    os.environ.setdefault("NO_AT_BRIDGE", "1")

    try:
        import gi

        gi.require_version("Gtk", "4.0")
        from gi.repository import GLib

        from fnv_planner.ui.app import FnvPlannerApp

        app = FnvPlannerApp()

        timeout_ms = max(100, int(float(args.timeout) * 1000.0))

        def _quit_app() -> bool:
            app.quit()
            return False

        GLib.timeout_add(timeout_ms, _quit_app)
        app.run([])
        print(f"UI smoke passed (headless Broadway, timeout={args.timeout:.1f}s).")
        return 0
    except Exception as exc:  # pragma: no cover - runtime/system dependent
        print(f"UI smoke failed: {exc}")
        return 1
    finally:
        os.environ.clear()
        os.environ.update(old_env)
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)


if __name__ == "__main__":
    raise SystemExit(main())
