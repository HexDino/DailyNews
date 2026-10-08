#!/usr/bin/env python3
"""Demo screenshots: calendar panel open + followups expanded."""
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8765/index.html?date=2026-10-08"
OUT = Path("/opt/cursor/artifacts/screenshots")


def ensure_server():
    import urllib.request

    try:
        urllib.request.urlopen("http://127.0.0.1:8765/index.html", timeout=2)
        return None
    except Exception:
        pass
    proc = subprocess.Popen(
        [sys.executable, "-m", "http.server", "8765"],
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        try:
            urllib.request.urlopen("http://127.0.0.1:8765/index.html", timeout=1)
            return proc
        except Exception:
            time.sleep(0.2)
    raise RuntimeError("server failed")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    server = ensure_server()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for name, w, h in [("after-desktop-calendar-open", 1280, 900), ("after-mobile-calendar-open", 390, 844)]:
                ctx = browser.new_context(viewport={"width": w, "height": h})
                page = ctx.new_page()
                page.goto(BASE, wait_until="networkidle", timeout=60000)
                page.wait_for_selector(".calendar-strip-toggle")
                page.click(".calendar-strip-toggle")
                page.wait_for_selector("#calendar-panel-full:not([hidden])")
                page.locator("#theo-doi-tin-cu").evaluate("el => el.open = true")
                page.screenshot(path=str(OUT / f"{name}.png"), full_page=False)
                ctx.close()
            browser.close()
    finally:
        if server:
            server.terminate()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
