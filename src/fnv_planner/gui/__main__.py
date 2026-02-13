"""CLI entry point: python -m fnv_planner.gui [--esm PATH]"""

from __future__ import annotations

import argparse
import os
import sys


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="FNV Character Planner")
    parser.add_argument("--esm", type=str, default=None, help="Path to FalloutNV.esm")
    args = parser.parse_args(argv)

    if args.esm:
        os.environ["FNV_ESM_PATH"] = args.esm

    from fnv_planner.gui.app import FnvPlannerApp

    app = FnvPlannerApp()
    sys.exit(app.run(None))


if __name__ == "__main__":
    main()
