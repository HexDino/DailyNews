#!/usr/bin/env python3
"""Verify deployed GitHub Pages site (live URL)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

LIVE = "https://hexdino.github.io/DailyNews/index.html?date=2026-10-08"
ROOT = Path(__file__).resolve().parent.parent
OLD_CSS = ROOT / "scripts" / "_old_reader.css"


def load_old_css() -> str:
    if OLD_CSS.is_file():
        return OLD_CSS.read_text(encoding="utf-8")
    proc = subprocess.run(
        ["git", "show", "9c570f3:css/reader.css"],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        check=True,
    )
    OLD_CSS.write_text(proc.stdout, encoding="utf-8")
    return proc.stdout


def theme_metrics(page) -> dict:
    return page.evaluate(
        """() => {
      const btn = document.getElementById('btn-theme');
      const bb = btn ? btn.getBoundingClientRect() : null;
      const glyph = btn ? btn.querySelector('.theme-toggle-glyph:not([style*="display: none"])') || btn.querySelector('.theme-toggle-glyph') : null;
      const gb = glyph ? glyph.getBoundingClientRect() : null;
      return {
        btnH: bb ? bb.height : 0,
        btnW: bb ? bb.width : 0,
        glyphH: gb ? gb.height : 0,
        hasStrip: !!document.querySelector('.calendar-strip-wrap'),
        cssHref: document.querySelector('link[href*="reader.css"]')?.getAttribute('href') || '',
        jsSrc: document.querySelector('script[src*="reader.js"]')?.getAttribute('src') || '',
      };
    }"""
    )


def check_page(page, width: int, theme: str, label: str, errors: list[str]) -> None:
    page.set_viewport_size({"width": width, "height": 900 if width >= 768 else 844})
    page.goto(LIVE, wait_until="networkidle", timeout=120000)
    page.wait_for_selector("#btn-theme", timeout=60000)
    m = theme_metrics(page)
    if "reader.css?v=" not in m["cssHref"]:
        errors.append(f"{label}: css not cache-busted ({m['cssHref']})")
    if "reader.js?v=" not in m["jsSrc"]:
        errors.append(f"{label}: js not cache-busted ({m['jsSrc']})")
    if m["btnH"] > 56 or m["btnH"] < 36:
        errors.append(f"{label}: theme btn height {m['btnH']:.1f}px")
    if m["glyphH"] < 10:
        errors.append(f"{label}: theme glyph collapsed")
    if not m["hasStrip"]:
        errors.append(f"{label}: calendar strip missing")
    page.locator(".calendar-strip-toggle").click()
    page.wait_for_selector("#calendar-panel-full:not([hidden])", timeout=10000)
    page.locator(".calendar-panel-close").click()
    page.wait_for_function(
        "() => { const p = document.getElementById('calendar-panel-full'); return p && p.hidden; }"
    )


def main() -> int:
    errors: list[str] = []
    old_css = load_old_css()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for width in (390, 1280):
            for theme in ("light", "dark"):
                ctx = browser.new_context(color_scheme=theme)
                ctx.add_init_script(
                    f'localStorage.setItem("dailynews-theme","{theme}");'
                    'localStorage.setItem("dailynews-calendar-open","0");'
                )
                page = ctx.new_page()
                label = f"{width}px {theme}"
                try:
                    check_page(page, width, theme, label, errors)
                except Exception as e:
                    errors.append(f"{label}: {e}")
                if width == 390:
                    page.locator(".site-bar").screenshot(
                        path=f"/opt/cursor/artifacts/screenshots/live-header-390-{theme}.png"
                    )
                if width == 1280 and theme == "light":
                    page.set_viewport_size({"width": 1280, "height": 720})
                    page.goto(LIVE, wait_until="networkidle")
                    page.wait_for_selector(".calendar-strip-wrap", timeout=60000)
                    page.locator(".paper-sheet").screenshot(
                        path="/opt/cursor/artifacts/screenshots/live-top-1280-calendar.png"
                    )
                ctx.close()

        ctx = browser.new_context(viewport={"width": 390, "height": 844})
        page = ctx.new_page()
        page.route("**/css/reader.css**", lambda route: route.fulfill(
            body=old_css, content_type="text/css", status=200
        ))
        page.goto(LIVE, wait_until="networkidle", timeout=120000)
        page.wait_for_selector("#btn-theme")
        m = theme_metrics(page)
        if m["btnH"] > 80:
            errors.append(f"stale-css: theme btn exploded to {m['btnH']:.1f}px")
        if m["glyphH"] < 8:
            errors.append("stale-css: glyph invisible")
        ctx.close()
        browser.close()

    if errors:
        print("FAIL:", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    print("OK: live site verified")
    return 0


if __name__ == "__main__":
    sys.exit(main())
