#!/usr/bin/env python3
"""Smoke test: every issue loads without console errors; search queries work."""
from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = Path(__file__).resolve().parent
import sys

sys.path.insert(0, str(SCRIPTS))
from playwright_calendar import CALENDAR_ISSUE, CALENDAR_VIEWPORTS, exercise_calendar
from playwright_followups import (
    FOLLOWUPS_ISSUE,
    FOLLOWUPS_VIEWPORTS,
    assert_followup_pills,
    capture_followups_screenshots,
    exercise_followup_expand,
)
BASE_URL = "http://127.0.0.1:8765/"
SEARCH_QUERIES = ["claud haiku", "messy argentina", "ifcopenshel", "bong da"]


def ensure_server() -> subprocess.Popen | None:
    import urllib.request

    try:
        urllib.request.urlopen(BASE_URL + "index.html", timeout=2)
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
            urllib.request.urlopen(BASE_URL + "index.html", timeout=1)
            return proc
        except Exception:
            time.sleep(0.2)
    proc.kill()
    raise RuntimeError("Could not start local HTTP server on 8765")


def load_issues():
    idx = json.loads((ROOT / "issues/index.json").read_text(encoding="utf-8"))
    return [i["date"] for i in idx["issues"]]


def main() -> int:
    server = ensure_server()
    errors: list[str] = []
    issues = load_issues()

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for iid in issues:
                for theme in ("light", "dark"):
                    ctx = browser.new_context(
                        viewport={"width": 1280, "height": 800},
                        color_scheme=theme,
                    )
                    ctx.add_init_script(
                        f'localStorage.setItem("dailynews-theme", "{theme}");'
                    )
                    page = ctx.new_page()
                    logs: list[str] = []
                    page.on(
                        "console",
                        lambda msg: logs.append(msg.text)
                        if msg.type == "error"
                        else None,
                    )
                    page.on("pageerror", lambda exc: logs.append(str(exc)))
                    url = f"{BASE_URL}index.html?date={iid}"
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_selector("#paper-root .masthead", timeout=30000)
                    except Exception as e:
                        errors.append(f"{iid} ({theme}): load failed: {e}")
                        ctx.close()
                        continue
                    for line in logs:
                        errors.append(f"{iid} ({theme}): console: {line}")
                    for a in page.locator(".toc-link[href^='#']").all():
                        href = a.get_attribute("href") or ""
                        aid = href[1:]
                        if aid and aid != "muc-luc":
                            if page.locator(f"#{aid}").count() == 0:
                                errors.append(f"{iid}: missing anchor #{aid}")
                    ctx.close()

            ctx = browser.new_context(viewport={"width": 390, "height": 844})
            page = ctx.new_page()
            logs = []
            page.on(
                "console",
                lambda msg: logs.append(msg.text) if msg.type == "error" else None,
            )
            page.goto(f"{BASE_URL}archive.html", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("#archive-list li", timeout=30000)
            for line in logs:
                errors.append(f"archive: console: {line}")
            ctx.close()

            ctx = browser.new_context(viewport={"width": 1280, "height": 800})
            page = ctx.new_page()
            page.goto(f"{BASE_URL}index.html", wait_until="domcontentloaded")
            page.wait_for_selector("#search-input")
            for q in SEARCH_QUERIES:
                page.fill("#search-input", q)
                page.evaluate(
                    "document.getElementById('search-form').requestSubmit()"
                )
                page.wait_for_selector("#search-panel:not([hidden])", timeout=15000)
                page.wait_for_timeout(350)
                status = page.locator("#search-status").inner_text()
                if "Không có kết quả" in status:
                    errors.append(f"search: no hits for {q!r} ({status})")
            ctx.close()

            for w in CALENDAR_VIEWPORTS:
                for theme in ("light", "dark"):
                    ctx = browser.new_context(
                        viewport={"width": w, "height": 900 if w >= 768 else 844},
                        color_scheme=theme,
                    )
                    ctx.add_init_script(
                        f'localStorage.setItem("dailynews-theme", "{theme}");'
                        f'localStorage.setItem("dailynews-calendar-open", "0");'
                    )
                    page = ctx.new_page()
                    page.goto(
                        f"{BASE_URL}index.html?date={CALENDAR_ISSUE}",
                        wait_until="domcontentloaded",
                        timeout=60000,
                    )
                    page.wait_for_selector(".calendar-strip-toggle", timeout=30000)
                    errors.extend(
                        exercise_calendar(page, w, theme, "smoke")
                    )
                    ctx.close()

            for w in FOLLOWUPS_VIEWPORTS:
                for theme in ("light", "dark"):
                    ctx = browser.new_context(
                        viewport={"width": w, "height": 900 if w >= 768 else 844},
                        color_scheme=theme,
                    )
                    ctx.add_init_script(
                        f'localStorage.setItem("dailynews-theme", "{theme}");'
                    )
                    page = ctx.new_page()
                    page.goto(
                        f"{BASE_URL}index.html?date={FOLLOWUPS_ISSUE}",
                        wait_until="domcontentloaded",
                        timeout=60000,
                    )
                    page.wait_for_selector("#theo-doi-tin-cu", timeout=30000)
                    errors.extend(assert_followup_pills(page, w, theme, "smoke"))
                    errors.extend(exercise_followup_expand(page, w, theme, "smoke"))
                    ctx.close()

            capture_followups_screenshots(browser, BASE_URL)

            browser.close()
    finally:
        if server:
            server.terminate()
            server.wait(timeout=5)

    if errors:
        print(f"FAIL ({len(errors)}):", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    print(f"OK: smoke passed ({len(issues)} issues, search queries verified)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
