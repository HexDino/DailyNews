#!/usr/bin/env python3
"""Shared Playwright checks for the Lịch sự kiện calendar UI."""
from __future__ import annotations

from playwright.sync_api import Page

CALENDAR_ISSUE = "2026-10-08"
CALENDAR_VIEWPORTS = (1280, 1024, 768, 390)


def _calendar_state(page: Page) -> dict:
    return page.evaluate(
        """() => {
      const panel = document.getElementById('calendar-panel-full');
      const backdrop = document.querySelector('.calendar-backdrop');
      const mobile = window.matchMedia('(max-width: 640px)').matches;
      const panelBox = panel && !panel.hidden ? panel.getBoundingClientRect() : null;
      const backdropVisible = backdrop && !backdrop.hidden && getComputedStyle(backdrop).display !== 'none';
      return {
        mobile,
        panelOpen: !!(panel && !panel.hidden),
        backdropVisible,
        bodyLocked: document.body.classList.contains('calendar-sheet-open'),
        panelTop: panelBox ? panelBox.top : null,
        panelHeight: panelBox ? panelBox.height : null,
        panelCenterY: panelBox ? panelBox.top + panelBox.height / 2 : null,
        viewportH: window.innerHeight,
        sourceCount: panel ? panel.querySelectorAll('.source-link').length : 0,
      };
    }"""
    )


def exercise_calendar(page: Page, width: int, theme: str, label: str) -> list[str]:
    """Open/close calendar via strip, header, Esc; verify backdrop and links."""
    errors: list[str] = []
    if not page.locator(".calendar-strip-wrap").count():
        return errors

    def assert_state(want_open: bool, ctx: str) -> None:
        st = _calendar_state(page)
        if want_open != st["panelOpen"]:
            errors.append(f"{label} {width}px {theme} {ctx}: panel open={st['panelOpen']}")
        if st["mobile"]:
            if want_open and not st["backdropVisible"]:
                errors.append(f"{label} {width}px {theme} {ctx}: mobile backdrop missing")
            if want_open and not st["bodyLocked"]:
                errors.append(f"{label} {width}px {theme} {ctx}: mobile body not locked")
            if want_open and st["panelCenterY"] is not None:
                mid = st["viewportH"] / 2
                if abs(st["panelCenterY"] - mid) > st["viewportH"] * 0.22:
                    errors.append(
                        f"{label} {width}px {theme} {ctx}: panel not centered"
                    )
                if st["panelTop"] is not None and st["panelTop"] < 8:
                    errors.append(f"{label} {width}px {theme} {ctx}: panel too high")
        else:
            if st["backdropVisible"]:
                errors.append(f"{label} {width}px {theme} {ctx}: desktop backdrop visible")
            if st["bodyLocked"]:
                errors.append(f"{label} {width}px {theme} {ctx}: desktop body locked")

    page.locator(".calendar-strip-toggle").click()
    page.wait_for_selector("#calendar-panel-full:not([hidden])", timeout=5000)
    assert_state(True, "strip open")

    link = page.locator("#calendar-panel-full .source-link").first
    if link.count():
        href = link.get_attribute("href") or ""
        if not href.startswith("http"):
            errors.append(f"{label} {width}px {theme}: calendar source missing href")
        else:
            box = link.bounding_box()
            if not box or box["width"] < 2:
                errors.append(f"{label} {width}px {theme}: source link not clickable")

    page.locator(".calendar-panel-close").click()
    page.wait_for_function(
        "() => { const p = document.getElementById('calendar-panel-full'); return p && p.hidden; }",
        timeout=5000,
    )
    assert_state(False, "close button")

    st = _calendar_state(page)
    if st["backdropVisible"] or st["bodyLocked"]:
        errors.append(f"{label} {width}px {theme}: backdrop/body stuck after close")

    page.locator("#btn-calendar").click()
    page.wait_for_selector("#calendar-panel-full:not([hidden])", timeout=5000)
    assert_state(True, "header open")

    page.keyboard.press("Escape")
    page.wait_for_function(
        "() => { const p = document.getElementById('calendar-panel-full'); return p && p.hidden; }",
        timeout=5000,
    )
    assert_state(False, "escape close")

    st = _calendar_state(page)
    if st["backdropVisible"] or st["bodyLocked"]:
        errors.append(f"{label} {width}px {theme}: stuck after Esc")

    return errors
