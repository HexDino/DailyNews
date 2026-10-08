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
      const toggle = document.querySelector('.calendar-strip-toggle');
      return {{
        mobile,
        panelCount: document.querySelectorAll('#calendar-panel-full').length,
        panelOpen: !!(panel && !panel.hidden),
        panelModal: !!(panel && panel.classList.contains('calendar-panel--open')),
        panelInBody: panel?.parentElement === document.body,
        teaserVisible: !!(document.querySelector('.calendar-teaser-bar') && getComputedStyle(document.querySelector('.calendar-teaser-bar')).display !== 'none'),
        backdropVisible,
        bodyLocked: document.body.classList.contains('calendar-sheet-open'),
        panelTop: panelBox ? panelBox.top : null,
        panelHeight: panelBox ? panelBox.height : null,
        panelCenterY: panelBox ? panelBox.top + panelBox.height / 2 : null,
        viewportH: window.innerHeight,
        sourceCount: panel ? panel.querySelectorAll('.source-link').length : 0,
        ariaExpanded: toggle?.getAttribute('aria-expanded') ?? null,
      }};
    }}"""
    )


def _assert_sources(page: Page, label: str, width: int, theme: str) -> list[str]:
    src_check = page.evaluate(
        """() => {
      const items = [...document.querySelectorAll('#calendar-panel-full .calendar-item')];
      const bad = [];
      items.forEach((it, i) => {
        const line = it.querySelector('.sources-line');
        if (!line) {
          bad.push(`item${i}: no sources line`);
          return;
        }
        const label = line.querySelector('.sources-label');
        if (!label || label.textContent.trim() !== 'Nguồn:') {
          bad.push(`item${i}: bad label`);
        }
        const links = line.querySelectorAll('.source-link');
        if (!links.length) bad.push(`item${i}: no source links`);
      });
      return bad;
    }"""
    )
    return [f"{label} {width}px {theme}: {b}" for b in src_check]


def _reset_calendar_dom(page: Page) -> None:
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


def exercise_calendar(page: Page, width: int, theme: str, label: str) -> list[str]:
    """Open/close calendar via real mouse coords, header, Esc; verify state."""
    errors: list[str] = []
    if not page.locator("#btn-calendar:not([hidden])").count():
        return errors

    panel_expr = _panel_js()
    _reset_calendar_dom(page)
    wait_open = f"() => {{ const p = {panel_expr}; return p && !p.hidden; }}"
    wait_closed = f"() => {{ const p = {panel_expr}; return p && p.hidden; }}"
    is_mobile = width <= 640

    def assert_state(want_open: bool, ctx: str) -> None:
        st = _calendar_state(page)
        if st["panelCount"] > 1:
            errors.append(
                f"{label} {width}px {theme} {ctx}: duplicate #calendar-panel-full ({st['panelCount']})"
            )
        if want_open != st["panelOpen"]:
            errors.append(f"{label} {width}px {theme} {ctx}: panel open={st['panelOpen']}")
        if st["ariaExpanded"] is not None:
            want_exp = "true" if want_open else "false"
            if st["ariaExpanded"] != want_exp:
                errors.append(
                    f"{label} {width}px {theme} {ctx}: aria-expanded={st['ariaExpanded']!r}"
                )
        if is_mobile:
            if st["teaserVisible"]:
                errors.append(f"{label} {width}px {theme} {ctx}: teaser visible on mobile")
            if want_open and not st["panelModal"]:
                errors.append(f"{label} {width}px {theme} {ctx}: mobile panel not modal")
            if want_open and not st["panelInBody"]:
                errors.append(f"{label} {width}px {theme} {ctx}: mobile panel not portaled")
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
            if not want_open and st["panelOpen"] is False:
                inline = page.evaluate(
                    """() => {
                  const p = document.querySelector('#lich-su-kien #calendar-panel-full');
                  if (!p || p.hidden) return false;
                  return p.parentElement !== document.body;
                }"""
                )
                if inline:
                    errors.append(
                        f"{label} {width}px {theme} {ctx}: inline calendar in page flow"
                    )
        else:
            if st["backdropVisible"]:
                errors.append(f"{label} {width}px {theme} {ctx}: desktop backdrop visible")
            if st["bodyLocked"]:
                errors.append(f"{label} {width}px {theme} {ctx}: desktop body locked")

    st = _calendar_state(page)
    if is_mobile and (st["teaserVisible"] or st["panelOpen"]):
        errors.append(f"{label} {width}px {theme}: calendar chrome visible on load")

    if is_mobile:
        page.evaluate("localStorage.setItem('dallynews-calendar-open', '1')")
        page.reload(wait_until="domcontentloaded")
        page.wait_for_selector("#btn-calendar:not([hidden])", timeout=30000)
        st = _calendar_state(page)
        if st["panelOpen"]:
            errors.append(
                f"{label} {width}px {theme}: auto-opened modal from localStorage"
            )
        _reset_calendar_dom(page)

    if not is_mobile:
        try:
            mouse_click_locator(page, ".calendar-strip-toggle")
        except RuntimeError as e:
            errors.append(f"{label} {width}px {theme}: strip toggle mouse: {e}")
            return errors
        page.wait_for_function(wait_open, timeout=5000)
        assert_state(True, "strip open")
        errors.extend(_assert_sources(page, label, width, theme))
        try:
            mouse_click_locator(page, ".calendar-panel-close")
        except RuntimeError as e:
            errors.append(f"{label} {width}px {theme}: close mouse: {e}")
            return errors
        page.wait_for_function(wait_closed, timeout=5000)
        assert_state(False, "close button")

    try:
        mouse_click_locator(page, "#btn-calendar")
    except RuntimeError as e:
        errors.append(f"{label} {width}px {theme}: header calendar mouse: {e}")
        return errors
    page.wait_for_function(wait_open, timeout=5000)
    assert_state(True, "header open")
    errors.extend(_assert_sources(page, label, width, theme))

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

    mouse_click_locator(page, "#btn-calendar")
    page.wait_for_function(wait_open, timeout=5000)
    page.keyboard.press("Escape")
    page.wait_for_function(wait_closed, timeout=5000)
    assert_state(False, "escape close")

    if is_mobile:
        mouse_click_locator(page, "#btn-calendar")
        page.wait_for_function(wait_open, timeout=5000)
        page.locator('button[data-tag-id="tech"]').click(force=True)
        page.wait_for_timeout(600)
        st = _calendar_state(page)
        if st["panelCount"] > 1:
            errors.append(
                f"{label} {width}px {theme}: orphan panel after tag rerender"
            )
        if st["panelOpen"]:
            try:
                mouse_click_locator(page, ".calendar-panel-close")
            except RuntimeError as e:
                errors.append(f"{label} {width}px {theme}: close after rerender: {e}")
            else:
                page.wait_for_function(wait_closed, timeout=5000)
        assert_state(False, "after tag rerender")

    return errors
