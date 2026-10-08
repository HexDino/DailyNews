#!/usr/bin/env python3
"""Capture layout screenshots for before/after comparison."""
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8765/index.html?date=2026-10-08"
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/opt/cursor/artifacts/screenshots")
PREFIX = sys.argv[2] if len(sys.argv) > 2 else "layout"


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
            for name, w, h in [
                ("desktop-1280", 1280, 900),
                ("mobile-390", 390, 844),
            ]:
                ctx = browser.new_context(viewport={"width": w, "height": h})
                page = ctx.new_page()
                page.goto(BASE, wait_until="networkidle", timeout=60000)
                page.wait_for_selector("#paper-root .masthead")
                page.screenshot(path=str(OUT / f"{PREFIX}-{name}.png"), full_page=True)
                ctx.close()
            browser.close()
    finally:
        if server:
            server.terminate()
            server.wait(timeout=5)
    print(f"Saved to {OUT} with prefix {PREFIX}")


if __name__ == "__main__":
    main()
