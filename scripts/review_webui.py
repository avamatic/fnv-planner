"""Autonomous UI review: interact with web UI and capture review artifacts."""

from __future__ import annotations

import argparse
import json
import socket
import threading
import time
from pathlib import Path

from fnv_planner.webui.server import WEBUI_DIR, make_server


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    _host, port = sock.getsockname()
    sock.close()
    return int(port)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Playwright UI review and emit screenshots/report.")
    parser.add_argument("--out", type=Path, default=Path("artifacts/ui_review"))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise SystemExit(
            "Playwright is not installed. Run: pip install playwright && python -m playwright install chromium"
        ) from exc

    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)

    port = args.port or _free_port()
    server = make_server(args.host, port, WEBUI_DIR)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    time.sleep(0.2)

    base_url = f"http://{args.host}:{port}/index.html"
    checks: list[str] = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.set_default_timeout(120000)
            page.goto(base_url, wait_until="domcontentloaded")

            page.locator("#app-title").wait_for()
            page.locator("#meta-max-crit-dmg").wait_for()
            checks.append("Loaded app shell")
            page.screenshot(path=str(out / "01_build.png"), full_page=True)

            page.get_by_label("Max Crit Dmg").check()
            page.locator("#actor-value-select").select_option("32")
            page.locator("#actor-value-number").fill("90")
            page.locator("#actor-request-form button[type='submit']").click()
            page.locator("#perk-picker-search").fill("crit")
            checks.append("Exercised build controls and perk picker")
            page.screenshot(path=str(out / "01b_build_controls.png"), full_page=True)

            page.get_by_role("button", name="Progression").click()
            page.locator("#preview-level").fill("20")
            page.locator("#preview-level").dispatch_event("input")
            page.locator("#preview-level-value").wait_for()
            checks.append("Interacted with progression level slider")
            page.screenshot(path=str(out / "02_progression.png"), full_page=True)

            page.get_by_role("button", name="Library").click()
            page.locator("#gear-search").fill("rifle")
            gear_buttons = page.locator("button[data-equip-id]")
            if gear_buttons.count() > 0:
                gear_buttons.first.click()
            checks.append("Filtered gear catalog and attempted equip")
            page.screenshot(path=str(out / "03_library.png"), full_page=True)

            page.get_by_role("button", name="Diagnostics").click()
            checks.append("Opened diagnostics tab")
            page.screenshot(path=str(out / "04_diagnostics.png"), full_page=True)

            browser.close()
    finally:
        server.shutdown()
        server.server_close()

    report = {
        "status": "ok",
        "url": base_url,
        "checks": checks,
        "screenshots": [
            "01_build.png",
            "01b_build_controls.png",
            "02_progression.png",
            "03_library.png",
            "04_diagnostics.png",
        ],
    }
    (out / "report.json").write_text(json.dumps(report, indent=2))
    print(f"Review artifacts written to: {out}")
    print((out / "report.json").read_text())


if __name__ == "__main__":
    main()
