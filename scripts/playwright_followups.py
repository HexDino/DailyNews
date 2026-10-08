#!/usr/bin/env python3
"""Playwright checks for Theo dõi tin cũ follow-up rows."""
from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page

FOLLOWUPS_ISSUE = "2026-10-08"
FOLLOWUPS_VIEWPORTS = (1280, 1024, 768, 390)
ARTIFACT_DIR = Path("/opt/cursor/artifacts/screenshots")


def _open_followups_block(page: Page) -> None:
    block = page.locator("#theo-doi-tin-cu")
    if not block.count():
        return
    if block.evaluate("el => !el.open"):
        block.locator("> summary").click()


def assert_followup_pills(page: Page, width: int, theme: str, label: str) -> list[str]:
    """Pills stay single-line; no text spills outside the oval."""
    errors: list[str] = []
    if not page.locator(".followup-row").count():
        return errors

    _open_followups_block(page)

    result = page.evaluate(
        """() => {
      const pills = [...document.querySelectorAll('.followup-status')];
      return pills.map((pill, i) => {
        const style = getComputedStyle(pill);
        const fs = parseFloat(style.fontSize) || 14;
        let lh = parseFloat(style.lineHeight);
        if (Number.isNaN(lh)) lh = fs * 1.15;
        const rect = pill.getBoundingClientRect();
        const overflowX = pill.scrollWidth - pill.clientWidth;
        const overflowY = pill.scrollHeight - pill.clientHeight;
        const pad =
          parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
        const border =
          parseFloat(style.borderTopWidth) + parseFloat(style.borderBottomWidth);
        const maxHeight = lh * 1.6 + pad + border;
        return {
          i,
          height: rect.height,
          maxHeight,
          overflowX,
          overflowY,
          nowrap: style.whiteSpace === 'nowrap',
        };
      });
    }"""
    )

    for row in result:
        ctx = f"{label} {width}px {theme} pill[{row['i']}]"
        if row["height"] > row["maxHeight"] + 0.5:
            errors.append(
                f"{ctx}: height {row['height']:.1f}px > {row['maxHeight']:.1f}px (1.6em)"
            )
        if row["overflowX"] > 1 or row["overflowY"] > 1:
            errors.append(
                f"{ctx}: text overflow (x={row['overflowX']}, y={row['overflowY']})"
            )
        if not row["nowrap"]:
            errors.append(f"{ctx}: white-space not nowrap")

    return errors


def exercise_followup_expand(page: Page, width: int, theme: str, label: str) -> list[str]:
    errors: list[str] = []
    row = page.locator(".followup-row").first
    if not row.count():
        return errors

    _open_followups_block(page)

    preview = row.locator(".followup-preview")
    if not preview.count():
        errors.append(f"{label} {width}px {theme}: missing followup-preview")

    row.locator("summary").click()
    page.wait_for_selector(".followup-row[open] .followup-body", timeout=5000)
    if row.locator(".followup-body .source-link").count() == 0:
        errors.append(f"{label} {width}px {theme}: expanded row missing sources")

    row.locator("summary").click()
    page.wait_for_function(
        "() => !document.querySelector('.followup-row[open]')",
        timeout=5000,
    )
    return errors


def capture_followups_screenshots(browser, base_url: str) -> None:
    """Save follow-ups section at 1024 and 390 (light + dark)."""
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    for width in (1024, 390):
        height = 900 if width >= 768 else 844
        for theme in ("light", "dark"):
            ctx = browser.new_context(
                viewport={"width": width, "height": height},
                color_scheme=theme,
            )
            ctx.add_init_script(
                f'localStorage.setItem("dailynews-theme", "{theme}");'
            )
            shot_page = ctx.new_page()
            shot_page.goto(
                f"{base_url}index.html?date={FOLLOWUPS_ISSUE}",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            shot_page.wait_for_selector("#theo-doi-tin-cu", timeout=30000)
            _open_followups_block(shot_page)
            section = shot_page.locator("#theo-doi-tin-cu")
            section.scroll_into_view_if_needed()
            shot_page.wait_for_timeout(200)
            path = ARTIFACT_DIR / f"followups-{width}-{theme}.png"
            section.screenshot(path=str(path))
            ctx.close()
