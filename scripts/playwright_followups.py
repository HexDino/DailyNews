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


def assert_calendar_ui_chips(
    page: Page, width: int, theme: str, label: str
) -> list[str]:
    """Calendar teaser chips share height, radius, and sans UI typography."""
    errors: list[str] = []
    bar = page.locator(".calendar-teaser-bar")
    if not bar.count():
        return errors

    result = page.evaluate(
        """() => {
      const bar = document.querySelector('.calendar-teaser-bar');
      if (!bar) return null;
      const chips = [...bar.querySelectorAll('.ui-chip')].filter((el) => {
        const s = getComputedStyle(el);
        return s.display !== 'none' && s.visibility !== 'hidden';
      });
      const label = bar.querySelector('.calendar-teaser-label');
      const root = document.documentElement;
      const expectedH = parseFloat(getComputedStyle(root).getPropertyValue('--ui-chip-height')) || 22;
      const expectedR = parseFloat(getComputedStyle(root).getPropertyValue('--ui-chip-radius')) || 3;
      const chipData = chips.map((el, i) => {
        const s = getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        const br = parseFloat(s.borderTopLeftRadius) || 0;
        return {
          i,
          cls: el.className,
          height: rect.height,
          br,
          fs: parseFloat(s.fontSize),
          font: s.fontFamily,
          overflowY: el.scrollHeight - el.clientHeight,
        };
      });
      let labelFs = 0;
      if (label) labelFs = parseFloat(getComputedStyle(label).fontSize);
      return { expectedH, expectedR, chipData, labelFs };
    }"""
    )
    if not result:
        return errors

    for row in result["chipData"]:
        ctx = f"{label} {width}px {theme} chip[{row['i']}]"
        if abs(row["height"] - result["expectedH"]) > 1.5:
            errors.append(
                f"{ctx}: height {row['height']:.1f}px != {result['expectedH']}px"
            )
        if abs(row["br"] - result["expectedR"]) > 0.6:
            errors.append(f"{ctx}: radius {row['br']:.1f}px != {result['expectedR']}px")
        if row["overflowY"] > 1:
            errors.append(f"{ctx}: vertical text overflow")
        if row["fs"] < 11.5 or row["fs"] > 13.5:
            errors.append(f"{ctx}: font-size {row['fs']:.1f}px outside 12–13px")

    if result["labelFs"] and (
        result["labelFs"] < 11.5 or result["labelFs"] > 13.5
    ):
        errors.append(
            f"{label} {width}px {theme}: label font-size {result['labelFs']:.1f}px"
        )

    return errors


def assert_followup_pills(page: Page, width: int, theme: str, label: str) -> list[str]:
    """Status chips stay single-line; no text spills outside the chip."""
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
        const root = document.documentElement;
        const chipH =
          parseFloat(getComputedStyle(root).getPropertyValue('--ui-chip-height')) || 22;
        const maxHeight = Math.max(chipH, lh * 1.6 + pad + border);
        return {
          i,
          height: rect.height,
          maxHeight,
          chipH,
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
        if abs(row["height"] - row["chipH"]) > 1.5:
            errors.append(
                f"{ctx}: height {row['height']:.1f}px != ui-chip {row['chipH']}px"
            )

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


def capture_calendar_teaser_screenshots(browser, base_url: str) -> None:
    """Save Sắp diễn ra bar at 1280, 1024, 390 (light + dark)."""
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    for width in (1280, 1024, 390):
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
            shot_page.wait_for_selector(".calendar-teaser-bar", timeout=30000)
            bar = shot_page.locator(".calendar-strip-wrap")
            bar.scroll_into_view_if_needed()
            shot_page.wait_for_timeout(200)
            path = ARTIFACT_DIR / f"calendar-teaser-{width}-{theme}.png"
            bar.screenshot(path=str(path))
            ctx.close()


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
