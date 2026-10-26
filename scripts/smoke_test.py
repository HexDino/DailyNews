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
from playwright_calendar import (
    CALENDAR_ISSUE,
    CALENDAR_ISSUES_ARCHIVE,
    CALENDAR_VIEWPORTS,
    exercise_calendar_with_retry,
)
from playwright_followups import (
    FOLLOWUPS_ISSUE,
    FOLLOWUPS_VIEWPORTS,
    assert_calendar_ui_chips,
    assert_followup_pills,
    capture_calendar_panel_screenshots,
    capture_calendar_teaser_screenshots,
    capture_followups_screenshots,
    capture_mobile_page_top_screenshots,
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


def load_index():
    return json.loads((ROOT / "issues/index.json").read_text(encoding="utf-8"))


def load_issues():
    return [i["date"] for i in load_index()["issues"]]


def archive_filter_dates(index: dict, type_param: str | None) -> list[str]:
    issues = index["issues"]
    meta = {row["date"]: row for row in issues}
    ids = [row["date"] for row in issues]

    def edition_of(issue_id: str) -> str:
        row = meta.get(issue_id) or {}
        if row.get("edition") == "chieu" or issue_id.endswith("-chieu"):
            return "chieu"
        return "sang"

    if not type_param:
        return sorted(ids, reverse=True)
    if type_param == "chieu":
        filtered = [i for i in ids if edition_of(i) == "chieu"]
    elif type_param == "sang":
        filtered = [i for i in ids if edition_of(i) == "sang"]
    else:
        filtered = ids
    return sorted(filtered, reverse=True)


def main() -> int:
    server = ensure_server()
    errors: list[str] = []
    index = load_index()
    issues = [i["date"] for i in index["issues"]]

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

            archive_dates = archive_filter_dates(index, None)
            archive_page_size = 20
            archive_total_pages = max(
                1, (len(archive_dates) + archive_page_size - 1) // archive_page_size
            )

            ctx = browser.new_context(viewport={"width": 390, "height": 844})
            page = ctx.new_page()
            logs = []
            page.on(
                "console",
                lambda msg: logs.append(msg.text) if msg.type == "error" else None,
            )
            page.goto(f"{BASE_URL}archive.html", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("#archive-list li", timeout=30000)
            if page.locator(".archive-read-progress").count():
                errors.append("archive: read progress UI should be removed")
            if page.locator(".archive-type-chips button").count() != 3:
                errors.append("archive: expected three type filter chips")
            if page.locator("#archive-list li .badge-edition").count() != page.locator(
                "#archive-list li"
            ).count():
                errors.append("archive: each row should show an edition badge")
            if page.locator("#archive-list li").count() != min(
                archive_page_size, len(archive_dates)
            ):
                errors.append("archive: page 1 should show at most 20 issues")
            if archive_dates and page.locator(".archive-list .badge").filter(
                has_text="Mới nhất"
            ).count() != 1:
                errors.append("archive: newest badge should appear once on page 1")
            if archive_total_pages > 1:
                if page.locator("#archive-pagination").count() == 0:
                    errors.append("archive: missing pagination on page 1")
                page.locator(
                    '#archive-pagination a.archive-page-link[data-archive-page="2"]'
                ).click()
                page.wait_for_function(
                    "() => new URLSearchParams(location.search).get('page') === '2'"
                )
                expected_p2 = min(
                    archive_page_size,
                    len(archive_dates) - archive_page_size,
                )
                if page.locator("#archive-list li").count() != expected_p2:
                    errors.append(
                        f"archive: page 2 expected {expected_p2} issues"
                    )
                if page.locator(".archive-list .badge").filter(has_text="Mới nhất").count():
                    errors.append(
                        "archive: newest badge should only be on page 1"
                    )
            chieu_dates = archive_filter_dates(index, "chieu")
            page.locator('[data-archive-type="chieu"]').click()
            page.wait_for_function(
                "() => new URLSearchParams(location.search).get('type') === 'chieu'"
                " && !new URLSearchParams(location.search).get('page')"
            )
            expected_chieu_p1 = min(archive_page_size, len(chieu_dates))
            if page.locator("#archive-list li").count() != expected_chieu_p1:
                errors.append(
                    f"archive: chieu filter page 1 expected {expected_chieu_p1} issues"
                )
            if page.locator("#archive-list li .badge-edition").filter(
                has_text="Chiều"
            ).count() != expected_chieu_p1:
                errors.append("archive: chieu filter should only list evening editions")
            chieu_total_pages = max(
                1, (len(chieu_dates) + archive_page_size - 1) // archive_page_size
            )
            if chieu_total_pages > 1:
                page.locator(
                    '#archive-pagination a.archive-page-link[data-archive-page="2"]'
                ).click()
                page.wait_for_function(
                    "() => new URLSearchParams(location.search).get('type') === 'chieu'"
                    " && new URLSearchParams(location.search).get('page') === '2'"
                )
                expected_chieu_p2 = min(
                    archive_page_size,
                    len(chieu_dates) - archive_page_size,
                )
                if page.locator("#archive-list li").count() != expected_chieu_p2:
                    errors.append(
                        f"archive: chieu page 2 expected {expected_chieu_p2} issues"
                    )
            if page.locator('[data-archive-type="doc-cham"]').count():
                errors.append("archive: Đọc chậm filter chip should be removed")
            page.goto(f"{BASE_URL}archive.html?type=sang&page=999", wait_until="domcontentloaded")
            page.wait_for_selector("#archive-list li", timeout=30000)
            sang_dates = archive_filter_dates(index, "sang")
            sang_total_pages = max(
                1, (len(sang_dates) + archive_page_size - 1) // archive_page_size
            )
            page.wait_for_function(
                f"() => new URLSearchParams(location.search).get('page') === '{sang_total_pages}'"
                " && new URLSearchParams(location.search).get('type') === 'sang'"
            )
            for line in logs:
                errors.append(f"archive: console: {line}")
            ctx.close()

            ctx = browser.new_context(viewport={"width": 1280, "height": 800})
            page = ctx.new_page()
            page.goto(
                f"{BASE_URL}index.html?date={archive_dates[0]}",
                wait_until="domcontentloaded",
                timeout=60000,
            )
            page.wait_for_selector("#paper-root .article", timeout=30000)
            if page.locator(".read-toggle").count():
                errors.append("reader: read toggle should be removed")
            if page.locator("#read-progress").count():
                errors.append("reader: read progress should be removed")
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
                    page.wait_for_function(
                        "() => !!document.querySelector('#lich-su-kien')",
                        timeout=30000,
                    )
                    if page.locator("#btn-calendar").count():
                        errors.append(
                            f"smoke {w}px {theme}: header #btn-calendar should be removed"
                        )
                    brand_links = page.locator(".brand-cluster a.brand")
                    if brand_links.count() < 2:
                        errors.append(
                            f"smoke {w}px {theme}: missing Daily News / Slow Reads brand links"
                        )
                    elif "slow reads" not in (
                        brand_links.nth(1).text_content() or ""
                    ).lower():
                        errors.append(
                            f"smoke {w}px {theme}: second brand link should be Slow Reads"
                        )
                    if page.locator('.site-nav-desktop a[href*="slow-reads"]').count():
                        errors.append(
                            f"smoke {w}px {theme}: Slow Reads should not duplicate in right nav"
                        )
                    errors.extend(
                        exercise_calendar_with_retry(page, w, theme, "smoke")
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
                    errors.extend(assert_calendar_ui_chips(page, w, theme, "smoke"))
                    errors.extend(assert_followup_pills(page, w, theme, "smoke"))
                    errors.extend(exercise_followup_expand(page, w, theme, "smoke"))
                    ctx.close()

            for archive_id in CALENDAR_ISSUES_ARCHIVE:
                for w in (1024, 390):
                    for theme in ("light",):
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
                            f"{BASE_URL}index.html?date={archive_id}",
                            wait_until="domcontentloaded",
                            timeout=60000,
                        )
                        if page.locator("#lich-su-kien").count():
                            errors.extend(
                                exercise_calendar_with_retry(
                                    page, w, theme, f"archive-{archive_id}"
                                )
                            )
                        ctx.close()

            # Slow Reads library
            doc_index = json.loads(
                (ROOT / "slow-reads/articles/index.json").read_text(encoding="utf-8")
            )
            doc_articles = doc_index.get("articles") or []
            ctx = browser.new_context(viewport={"width": 390, "height": 844})
            page = ctx.new_page()
            logs = []
            page.on(
                "console",
                lambda msg: logs.append(msg.text) if msg.type == "error" else None,
            )
            page.goto(f"{BASE_URL}slow-reads/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_selector("#doc-cham-list .doc-cham-card", timeout=30000)
            if page.locator("#btn-calendar").count():
                errors.append("slow-reads: header calendar button should not exist")
            brand_links = page.locator(".brand-cluster a.brand")
            if brand_links.count() < 2 or "slow reads" not in (
                brand_links.nth(1).text_content() or ""
            ).lower():
                errors.append("slow-reads: missing Slow Reads brand link")
            if page.locator('.site-nav-desktop a[href="./"]').count():
                errors.append("slow-reads: Slow Reads should not duplicate in right nav")
            if "Slow Reads" not in page.title():
                errors.append("slow-reads: page title should include Slow Reads")
            if page.locator("main h1").inner_text().strip() != "Slow Reads":
                errors.append("slow-reads: h1 should be Slow Reads")
            expected_cards = min(20, len(doc_articles))
            if page.locator("#doc-cham-list .doc-cham-card").count() != expected_cards:
                errors.append(
                    f"slow-reads: expected {expected_cards} cards, got "
                    f"{page.locator('#doc-cham-list .doc-cham-card').count()}"
                )
            if page.locator("#doc-cham-filters .tag-chips button").count() < 9:
                errors.append("slow-reads: expected topic filter chips (Tất cả + topics)")
            # Active chip should be a flat solid fill (no edge mask smear).
            smear = page.evaluate(
                """() => {
                  const scroll = document.querySelector('#doc-cham-filters .tag-chips-scroll');
                  if (!scroll) return 'missing scroll';
                  const style = getComputedStyle(scroll);
                  const mask = style.maskImage || style.webkitMaskImage || 'none';
                  if (mask && mask !== 'none') return 'mask-image still set: ' + mask;
                  return '';
                }"""
            )
            if smear:
                errors.append(f"slow-reads: chip smear fix failed: {smear}")
            if doc_articles:
                first_id = doc_articles[0]["id"]
                page.goto(
                    f"{BASE_URL}slow-reads/article.html?id={first_id}",
                    wait_until="domcontentloaded",
                    timeout=60000,
                )
                page.wait_for_selector(".doc-cham-prose", timeout=30000)
                back = page.locator(".doc-cham-back a").first
                if back.count() == 0:
                    errors.append("slow-reads article: missing back link")
                elif "Slow Reads" not in back.inner_text():
                    errors.append("slow-reads article: back link should say Slow Reads")
                art = json.loads(
                    (ROOT / f"slow-reads/articles/{first_id}.json").read_text(
                        encoding="utf-8"
                    )
                )
                if art.get("lang") and art["lang"] != "vi":
                    if page.locator(".doc-cham-translated").count() == 0:
                        errors.append(
                            "slow-reads article: missing Bản dịch tiếng Việt note"
                        )
                has_star = any(
                    "*" in (b.get("text") or "") for b in (art.get("body") or [])
                )
                if has_star and page.locator(".doc-cham-prose em").count() == 0:
                    errors.append(
                        "slow-reads article: *...* markup should render as <em>"
                    )
            # Legacy /doc-cham/ redirect
            page.goto(f"{BASE_URL}doc-cham/", wait_until="domcontentloaded", timeout=60000)
            page.wait_for_url("**/slow-reads/**", timeout=15000)
            if "/slow-reads" not in page.url:
                errors.append("doc-cham redirect: should land on /slow-reads/")
            for line in logs:
                errors.append(f"slow-reads: console: {line}")
            ctx.close()

            capture_calendar_teaser_screenshots(browser, BASE_URL)
            capture_calendar_panel_screenshots(browser, BASE_URL)
            capture_mobile_page_top_screenshots(browser, BASE_URL)
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
