#!/usr/bin/env python3
"""Shared Playwright checks for the Lịch sự kiện calendar UI."""
from __future__ import annotations

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout

CALENDAR_ISSUE = "2026-10-10"
CALENDAR_VIEWPORTS = (1280, 1024, 768, 390)
CALENDAR_ISSUES_ARCHIVE = ("2026-10-07", "2026-10-07-chieu")
CALENDAR_WAIT_MS = 15000


def _panel_js() -> str:
    return """document.querySelector('#lich-su-kien #calendar-panel-full')
      || document.querySelector('body > #calendar-panel-full')"""


def mouse_click_locator(page: Page, selector: str) -> None:
    """Real mouse click at element center (not Playwright element.click())."""
    loc = page.locator(selector).first
    loc.scroll_into_view_if_needed(timeout=10000)
    box = loc.bounding_box()
    if not box or box["width"] < 1 or box["height"] < 1:
        raise RuntimeError(f"no box for {selector}")
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


def wait_calendar_open(page: Page, timeout: int = CALENDAR_WAIT_MS) -> None:
    panel_expr = _panel_js()
    page.wait_for_function(
        f"() => {{ const p = {panel_expr}; return p && !p.hidden; }}",
        timeout=timeout,
    )


def wait_calendar_closed(page: Page, timeout: int = CALENDAR_WAIT_MS) -> None:
    panel_expr = _panel_js()
    page.wait_for_function(
        f"""() => {{
      const p = {panel_expr};
      const bd = document.querySelector('.calendar-backdrop');
      const bdOk = !bd || bd.hidden || getComputedStyle(bd).display === 'none';
      return p && p.hidden && bdOk && !document.body.classList.contains('calendar-sheet-open');
    }}""",
        timeout=timeout,
    )


def close_calendar_ui(page: Page) -> None:
    """Close via ✕ with Esc fallback; wait until fully dismissed."""
    panel_expr = _panel_js()
    for attempt in range(2):
        open_now = page.evaluate(f"() => {{ const p = {panel_expr}; return !!(p && !p.hidden); }}")
        if not open_now:
            wait_calendar_closed(page)
            return
        try:
            mouse_click_locator(page, ".calendar-panel-close")
        except RuntimeError:
            page.keyboard.press("Escape")
        try:
            wait_calendar_closed(page, timeout=8000 if attempt == 0 else CALENDAR_WAIT_MS)
            return
        except PlaywrightTimeout:
            page.keyboard.press("Escape")
    wait_calendar_closed(page)


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
        if (!line) return;
        const srcLabel = line.querySelector('.sources-label');
        if (!srcLabel || srcLabel.textContent.trim() !== 'Nguồn:') {
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

    _reset_calendar_dom(page)
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
        else:
            if st["backdropVisible"]:
                errors.append(f"{label} {width}px {theme} {ctx}: desktop backdrop visible")
            if st["bodyLocked"]:
                errors.append(f"{label} {width}px {theme} {ctx}: desktop body locked")

    st = _calendar_state(page)
    if is_mobile and (st["teaserVisible"] or st["panelOpen"]):
        errors.append(f"{label} {width}px {theme}: calendar chrome visible on load")

    if is_mobile:
        toc = page.locator('a.toc-link[href="#lich-su-kien"]')
        if not toc.count():
            errors.append(f"{label} {width}px {theme}: missing toc calendar link")
        else:
            toc.scroll_into_view_if_needed()
        try:
            mouse_click_locator(page, 'a.toc-link[href="#lich-su-kien"]')
        except RuntimeError as e:
            errors.append(f"{label} {width}px {theme}: toc calendar mouse: {e}")
        else:
            wait_calendar_open(page)
            assert_state(True, "toc open")
            try:
                close_calendar_ui(page)
            except PlaywrightTimeout as e:
                errors.append(f"{label} {width}px {theme}: toc close: {e}")
            else:
                assert_state(False, "toc close")

        page.evaluate(
            """() => {
          localStorage.setItem('dailynews-calendar-open', '1');
          const u = new URL(location.href);
          u.hash = '';
          history.replaceState(null, '', u.pathname + u.search);
        }"""
        )
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
        wait_calendar_open(page)
        assert_state(True, "strip open")
        errors.extend(_assert_sources(page, label, width, theme))
        try:
            close_calendar_ui(page)
        except PlaywrightTimeout as e:
            errors.append(f"{label} {width}px {theme}: strip close: {e}")
            return errors
        assert_state(False, "close button")

    try:
        mouse_click_locator(page, "#btn-calendar")
    except RuntimeError as e:
        errors.append(f"{label} {width}px {theme}: header calendar mouse: {e}")
        return errors
    wait_calendar_open(page)
    assert_state(True, "header open")
    errors.extend(_assert_sources(page, label, width, theme))

    try:
        close_calendar_ui(page)
    except PlaywrightTimeout as e:
        errors.append(f"{label} {width}px {theme}: header close: {e}")
        return errors
    assert_state(False, "close button")

    st = _calendar_state(page)
    if st["backdropVisible"] or st["bodyLocked"]:
        errors.append(f"{label} {width}px {theme}: backdrop/body stuck after close")

    mouse_click_locator(page, "#btn-calendar")
    wait_calendar_open(page)
    page.keyboard.press("Escape")
    wait_calendar_closed(page)
    assert_state(False, "escape close")

    if is_mobile:
        mouse_click_locator(page, "#btn-calendar")
        wait_calendar_open(page)
        page.locator('button[data-tag-id="tech"]').click(force=True)
        page.wait_for_timeout(600)
        st = _calendar_state(page)
        if st["panelCount"] > 1:
            errors.append(
                f"{label} {width}px {theme}: orphan panel after tag rerender"
            )
        if st["panelOpen"]:
            try:
                close_calendar_ui(page)
            except PlaywrightTimeout as e:
                errors.append(f"{label} {width}px {theme}: close after rerender: {e}")
        assert_state(False, "after tag rerender")

    return errors


def exercise_calendar_with_retry(
    page: Page, width: int, theme: str, label: str, retries: int = 1
) -> list[str]:
    """Run exercise_calendar; on timeout/exception retry once after reset."""
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            errs = exercise_calendar(page, width, theme, label)
            if errs:
                return errs
            return []
        except PlaywrightTimeout as e:
            last_exc = e
            if attempt >= retries:
                return [f"{label} {width}px {theme}: calendar exercise timeout: {e}"]
            _reset_calendar_dom(page)
            page.wait_for_timeout(400)
    if last_exc:
        return [f"{label} {width}px {theme}: calendar exercise failed: {last_exc}"]
    return []
