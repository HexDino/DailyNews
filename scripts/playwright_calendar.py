#!/usr/bin/env python3
"""Shared Playwright checks for the Lịch sự kiện calendar UI."""
from __future__ import annotations

from playwright.sync_api import Page

CALENDAR_ISSUE = "2026-10-08"
CALENDAR_VIEWPORTS = (1280, 1024, 768, 390)
CALENDAR_ISSUES_ARCHIVE = ("2026-10-07", "2026-10-07-chieu")


def _panel_js() -> str:
    return """document.querySelector('#lich-su-kien #calendar-panel-full')
      || document.querySelector('body > #calendar-panel-full')"""


def mouse_click_locator(page: Page, selector: str) -> None:
    """Real mouse click at element center (not Playwright element.click())."""
    loc = page.locator(selector).first
    box = loc.bounding_box()
    if not box or box["width"] < 1 or box["height"] < 1:
        raise RuntimeError(f"no box for {selector}")
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def _calendar_state(page: Page) -> dict:
    panel_expr = _panel_js()
    return page.evaluate(
        f"""() => {{
      const panel = {panel_expr};
      const backdrop = document.querySelector('.calendar-backdrop');
      const mobile = window.matchMedia('(max-width: 640px)').matches;
      const panelBox = panel && !panel.hidden ? panel.getBoundingClientRect() : null;
      const backdropVisible = backdrop && !backdrop.hidden && getComputedStyle(backdrop).display !== 'none';
      return {{
        mobile,
        panelCount: document.querySelectorAll('#calendar-panel-full').length,
        panelOpen: !!(panel && !panel.hidden),
        backdropVisible,
        bodyLocked: document.body.classList.contains('calendar-sheet-open'),
        panelTop: panelBox ? panelBox.top : null,
        panelHeight: panelBox ? panelBox.height : null,
        panelCenterY: panelBox ? panelBox.top + panelBox.height / 2 : null,
        viewportH: window.innerHeight,
        sourceCount: panel ? panel.querySelectorAll('.source-link').length : 0,
        ariaExpanded: document.querySelector('.calendar-strip-toggle')?.getAttribute('aria-expanded'),
      }};
    }}"""
    )


def exercise_calendar(page: Page, width: int, theme: str, label: str) -> list[str]:
    """Open/close calendar via real mouse coords, header, Esc; verify state."""
    errors: list[str] = []
    if not page.locator(".calendar-strip-wrap").count():
        return errors

    panel_expr = _panel_js()
    page.evaluate(
        f"""() => {{
      try {{ localStorage.setItem('dailynews-calendar-open', '0'); }} catch {{}}
      const panel = {panel_expr};
      const toggle = document.querySelector('.calendar-strip-toggle');
      const host = document.querySelector('#lich-su-kien');
      if (panel && host && panel.parentElement === document.body) {{
        host.appendChild(panel);
      }}
      if (panel) panel.hidden = true;
      panel?.classList.remove('calendar-panel--open');
      toggle?.setAttribute('aria-expanded', 'false');
      document.body.classList.remove('calendar-sheet-open');
      const bd = document.querySelector('.calendar-backdrop');
      if (bd) bd.hidden = true;
    }}"""
    )

    def assert_state(want_open: bool, ctx: str) -> None:
        st = _calendar_state(page)
        if st["panelCount"] > 1:
            errors.append(
                f"{label} {width}px {theme} {ctx}: duplicate #calendar-panel-full ({st['panelCount']})"
            )
        if want_open != st["panelOpen"]:
            errors.append(f"{label} {width}px {theme} {ctx}: panel open={st['panelOpen']}")
        want_exp = "true" if want_open else "false"
        if st["ariaExpanded"] != want_exp:
            errors.append(
                f"{label} {width}px {theme} {ctx}: aria-expanded={st['ariaExpanded']!r}"
            )
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

    wait_open = f"() => {{ const p = {panel_expr}; return p && !p.hidden; }}"
    wait_closed = f"() => {{ const p = {panel_expr}; return p && p.hidden; }}"

    try:
        mouse_click_locator(page, ".calendar-strip-toggle")
    except RuntimeError as e:
        errors.append(f"{label} {width}px {theme}: strip toggle mouse: {e}")
        return errors
    page.wait_for_function(wait_open, timeout=5000)
    assert_state(True, "strip open")

    link = page.locator("#calendar-panel-full .source-link").first
    if link.count():
        href = link.get_attribute("href") or ""
        if not href.startswith("http"):
            errors.append(f"{label} {width}px {theme}: calendar source missing href")

    try:
        mouse_click_locator(page, ".calendar-panel-close")
    except RuntimeError as e:
        errors.append(f"{label} {width}px {theme}: close mouse: {e}")
        return errors
    page.wait_for_function(wait_closed, timeout=5000)
    assert_state(False, "close button")

    st = _calendar_state(page)
    if st["backdropVisible"] or st["bodyLocked"]:
        errors.append(f"{label} {width}px {theme}: backdrop/body stuck after close")

    page.locator("#btn-calendar").click()
    page.wait_for_function(wait_open, timeout=5000)
    assert_state(True, "header open")

    page.keyboard.press("Escape")
    page.wait_for_function(wait_closed, timeout=5000)
    assert_state(False, "escape close")

    st = _calendar_state(page)
    if st["backdropVisible"] or st["bodyLocked"]:
        errors.append(f"{label} {width}px {theme}: stuck after Esc")

    if width <= 640:
        page.evaluate("localStorage.setItem('dailynews-calendar-open', '1')")
        mouse_click_locator(page, ".calendar-strip-toggle")
        page.wait_for_function(wait_open, timeout=5000)
        page.locator('button[data-tag-id="tech"]').click(force=True)
        page.wait_for_timeout(600)
        st = _calendar_state(page)
        if st["panelCount"] > 1:
            errors.append(
                f"{label} {width}px {theme}: orphan panel after tag rerender"
            )
        try:
            mouse_click_locator(page, ".calendar-panel-close")
        except RuntimeError as e:
            errors.append(f"{label} {width}px {theme}: close after rerender: {e}")
        else:
            page.wait_for_function(wait_closed, timeout=5000)
            assert_state(False, "close after rerender")

    row = page.locator(".followup-row").first
    if row.count():
        block = page.locator("#theo-doi-tin-cu")
        if block.evaluate("el => !el.open"):
            block.locator("> summary").click()
        try:
            mouse_click_locator(page, ".followup-row summary")
        except RuntimeError:
            pass
        else:
            page.wait_for_selector(".followup-row[open]", timeout=5000)
            mouse_click_locator(page, ".followup-row summary")
            page.wait_for_function(
                "() => !document.querySelector('.followup-row[open]')", timeout=5000
            )

    return errors
