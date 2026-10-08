#!/usr/bin/env python3
"""Full-site audit (Playwright). Run: python3 scripts/audit_playwright.py"""
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
    assert_calendar_ui_chips,
    assert_followup_pills,
    exercise_followup_expand,
)
BASE_URL = "http://127.0.0.1:8765/"
VIEWPORTS = [(1280, 800), (768, 1024), (390, 844)]
THEMES = ["light", "dark"]


def ensure_server():
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
    raise RuntimeError("Could not start HTTP server")


def load_issues():
    idx = json.loads((ROOT / "issues/index.json").read_text(encoding="utf-8"))
    return idx["issues"]


def audit():
    server = ensure_server()
    issues = load_issues()
    errors = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for issue in issues:
                iid = issue["date"]
                url = f"{BASE_URL}index.html?date={iid}"
                for w, h in VIEWPORTS:
                    for theme in THEMES:
                        ctx = browser.new_context(
                            viewport={"width": w, "height": h},
                            color_scheme=theme,
                        )
                        ctx.add_init_script(
                            f'localStorage.setItem("dailynews-theme", "{theme}");'
                        )
                        page = ctx.new_page()
                        console_errs = []
                        page.on(
                            "console",
                            lambda msg: console_errs.append(msg.text)
                            if msg.type == "error"
                            else None,
                        )
                        page.on(
                            "pageerror",
                            lambda exc: console_errs.append(str(exc)),
                        )
                        try:
                            page.goto(url, wait_until="domcontentloaded", timeout=60000)
                            page.wait_for_selector("#paper-root .masthead", timeout=30000)
                        except Exception as e:
                            errors.append(f"{iid} {w}x{h} {theme}: load failed: {e}")
                            ctx.close()
                            continue

                        for ce in console_errs:
                            errors.append(f"{iid} {w}x{h} {theme}: console: {ce}")

                        for a in page.locator(".toc-link[href^='#']").all():
                            href = a.get_attribute("href") or ""
                            aid = href[1:]
                            if aid and aid != "muc-luc":
                                if page.locator(f"#{aid}").count() == 0:
                                    errors.append(f"{iid} {w}x{h}: missing anchor #{aid}")

                        overflow = page.evaluate(
                            """() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2"""
                        )
                        if overflow:
                            errors.append(f"{iid} {w}x{h} {theme}: horizontal overflow")

                        ctx.close()

            for w, h in VIEWPORTS:
                ctx = browser.new_context(viewport={"width": w, "height": h})
                page = ctx.new_page()
                console_errs = []
                page.on(
                    "console",
                    lambda msg: console_errs.append(msg.text)
                    if msg.type == "error"
                    else None,
                )
                page.goto(f"{BASE_URL}archive.html", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_selector("#archive-list li", timeout=30000)
                for ce in console_errs:
                    errors.append(f"archive {w}x{h}: console: {ce}")
                ctx.close()

            cal_url = f"{BASE_URL}index.html?date={CALENDAR_ISSUE}"
            for w in CALENDAR_VIEWPORTS:
                for theme in THEMES:
                    ctx = browser.new_context(
                        viewport={"width": w, "height": 900 if w >= 768 else 844},
                        color_scheme=theme,
                    )
                    ctx.add_init_script(
                        f'localStorage.setItem("dailynews-theme", "{theme}");'
                        f'localStorage.setItem("dailynews-calendar-open", "0");'
                    )
                    page = ctx.new_page()
                    try:
                        page.goto(cal_url, wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_selector(".calendar-strip-toggle", timeout=30000)
                        errors.extend(exercise_calendar(page, w, theme, CALENDAR_ISSUE))
                    except Exception as e:
                        errors.append(f"calendar {w}px {theme}: {e}")
                    ctx.close()

            fu_url = f"{BASE_URL}index.html?date={FOLLOWUPS_ISSUE}"
            for w in FOLLOWUPS_VIEWPORTS:
                for theme in THEMES:
                    ctx = browser.new_context(
                        viewport={"width": w, "height": 900 if w >= 768 else 844},
                        color_scheme=theme,
                    )
                    ctx.add_init_script(
                        f'localStorage.setItem("dailynews-theme", "{theme}");'
                    )
                    page = ctx.new_page()
                    try:
                        page.goto(fu_url, wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_selector("#theo-doi-tin-cu", timeout=30000)
                        errors.extend(
                            assert_calendar_ui_chips(page, w, theme, FOLLOWUPS_ISSUE)
                        )
                        errors.extend(
                            assert_followup_pills(page, w, theme, FOLLOWUPS_ISSUE)
                        )
                        errors.extend(
                            exercise_followup_expand(page, w, theme, FOLLOWUPS_ISSUE)
                        )
                    except Exception as e:
                        errors.append(f"followups {w}px {theme}: {e}")
                    ctx.close()

            browser.close()
    finally:
        if server:
            server.terminate()
            server.wait(timeout=5)

    return errors


if __name__ == "__main__":
    errs = audit()
    if errs:
        print(f"FAIL: {len(errs)} issue(s)", file=sys.stderr)
        for e in errs:
            print(e, file=sys.stderr)
        sys.exit(1)
    print("OK: audit passed")
