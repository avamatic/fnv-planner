"""Run the cross-platform web UI with fresh exported planner state."""

from __future__ import annotations

import argparse
from pathlib import Path

from fnv_planner.webui.server import serve


def main() -> None:
    parser = argparse.ArgumentParser(description="Run web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--no-open", action="store_true", help="Do not open a browser tab")
    parser.add_argument(
        "--esm",
        action="append",
        default=[],
        help="Plugin path to load (.esm/.esp). Pass multiple times for load order.",
    )
    args = parser.parse_args()
    plugin_paths = [Path(raw).expanduser() for raw in args.esm] or None

    serve(host=args.host, port=args.port, open_browser=not args.no_open, plugin_paths=plugin_paths)


if __name__ == "__main__":
    main()
