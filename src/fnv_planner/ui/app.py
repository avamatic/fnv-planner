"""Cross-platform app launcher.

This replaces the legacy GTK frontend with the web UI runtime.
"""

from __future__ import annotations

from fnv_planner.webui.server import serve


def main() -> None:
    serve(host="127.0.0.1", port=4173, open_browser=True)


if __name__ == "__main__":
    main()
