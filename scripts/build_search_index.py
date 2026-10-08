#!/usr/bin/env python3
"""Build issues/search-index.json for client-side fuzzy search (no per-issue fetch)."""
from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ISSUES = ROOT / "issues"
OUT = ISSUES / "search-index.json"
CHIEU_SUFFIX = "-chieu"
SNIPPET_MAX = 320


def remove_diacritics(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return s.replace("đ", "d").replace("Đ", "D")


def norm_search(s: str) -> str:
    return remove_diacritics(s).lower()


def slugify(text: str) -> str:
    t = remove_diacritics(text).lower()
    t = t.replace("&", " va ")
    t = re.sub(r"[^a-z0-9\s-]", "", t)
    t = t.strip()
    t = re.sub(r"\s+", "-", t)
    return re.sub(r"-+", "-", t)


def section_label(sec: dict) -> str:
    if sec.get("topic"):
        if sec.get("subtitle"):
            return f"{sec['topic']} · {sec['subtitle']}"
        return sec["topic"]
    return sec.get("title") or ""


def article_dom_id(issue_id: str, sec: dict, item_index: int) -> str:
    if sec.get("topic"):
        if sec.get("subtitle"):
            sec_key = slugify(f"{sec['topic']} {sec['subtitle']}")
        else:
            sec_key = slugify(sec["topic"])
    else:
        sec_key = slugify(sec.get("title") or "")
    return f"art-{issue_id}-{sec_key}-{item_index}"


def parse_issue_id(issue_id: str) -> tuple[str, str | None]:
    if issue_id.endswith(CHIEU_SUFFIX):
        return issue_id[: -len(CHIEU_SUFFIX)], "chieu"
    return issue_id, None


def item_search_text(item: dict, sec: dict) -> str:
    parts = [
        item.get("headline"),
        item.get("meta"),
        sec.get("title"),
        sec.get("topic"),
        sec.get("subtitle"),
        sec.get("intro"),
    ]
    body = item.get("body")
    if body:
        if isinstance(body, list):
            parts.extend(body)
        else:
            parts.append(body)
    for src in item.get("sources") or []:
        parts.append(src.get("name"))
    return " ".join(p for p in parts if p)


def snippet_source(item: dict) -> str:
    body = item.get("body")
    if body:
        if isinstance(body, list) and body:
            return str(body[0])
        if isinstance(body, str):
            return body
    return item.get("headline") or item.get("meta") or ""


def short_text(s: str, max_len: int = SNIPPET_MAX) -> str:
    s = " ".join(s.split())
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def content_fingerprint(folders: list[Path]) -> str:
    h = hashlib.sha256()
    for folder in sorted(folders, key=lambda p: p.name):
        p = folder / "content.json"
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()[:16]


def issue_sort_key(folder_name: str) -> tuple[str, int]:
    if folder_name.endswith(CHIEU_SUFFIX):
        return (folder_name[: -len(CHIEU_SUFFIX)], 1)
    return (folder_name, 0)


def main() -> None:
    folders = sorted(
        (p for p in ISSUES.iterdir() if p.is_dir() and (p / "content.json").is_file()),
        key=lambda p: issue_sort_key(p.name),
    )
    if not folders:
        raise SystemExit("No issues found")

    version = content_fingerprint(folders)
    issue_ids = [p.name for p in folders]
    recency = {iid: rank + 1 for rank, iid in enumerate(issue_ids)}
    entries: list[dict] = []

    for folder in folders:
        issue_id = folder.name
        data = json.loads((folder / "content.json").read_text(encoding="utf-8"))
        cal_date, edition = parse_issue_id(issue_id)
        base = {
            "issueId": issue_id,
            "edition": edition,
            "date": data.get("date") or cal_date,
            "recencyRank": recency.get(issue_id, 0),
        }

        def push_row(
            *,
            kind: str,
            article_id: str,
            section: str,
            headline: str,
            text: str,
            snippet: str,
            topic=None,
            subsection=None,
        ) -> None:
            entries.append(
                {
                    **base,
                    "kind": kind,
                    "articleId": article_id,
                    "section": section,
                    "topic": topic,
                    "subsection": subsection,
                    "headline": headline,
                    "normHeadline": norm_search(headline),
                    "normText": norm_search(text),
                    "snippetSource": short_text(snippet),
                }
            )

        for sec in data.get("sections") or []:
            for i, item in enumerate(sec.get("items") or []):
                text = item_search_text(item, sec)
                push_row(
                    kind="article",
                    article_id=article_dom_id(issue_id, sec, i),
                    section=section_label(sec),
                    headline=item.get("headline") or "",
                    text=text,
                    snippet=snippet_source(item),
                    topic=sec.get("topic"),
                    subsection=sec.get("subtitle"),
                )

        for fi, fu in enumerate(data.get("followups") or []):
            text = " ".join(
                p
                for p in [
                    fu.get("title"),
                    fu.get("update"),
                    fu.get("status"),
                    fu.get("first_issue"),
                ]
                if p
            )
            for src in fu.get("sources") or []:
                text += " " + (src.get("name") or "")
            push_row(
                kind="followup",
                article_id=f"followup-{fi}",
                section="Theo dõi tin cũ",
                headline=fu.get("title") or "",
                text=text,
                snippet=fu.get("update") or fu.get("title") or "",
            )

        for ci, ev in enumerate(data.get("calendar") or []):
            text = " ".join(
                p
                for p in [
                    ev.get("title"),
                    ev.get("date"),
                    ev.get("time"),
                    ev.get("topic"),
                    ev.get("note"),
                ]
                if p
            )
            for src in ev.get("sources") or []:
                text += " " + (src.get("name") or "")
            ev_date = ev.get("date") or ""
            push_row(
                kind="calendar",
                article_id=f"calendar-{ev_date}-{ci}",
                section="Lịch sự kiện",
                headline=ev.get("title") or "",
                text=text,
                snippet=ev.get("note") or ev.get("title") or "",
                topic=ev.get("topic"),
                subsection=ev_date,
            )

    index = {"version": version, "entryCount": len(entries), "entries": entries}
    OUT.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Search index: {OUT.name} version={version} entries={len(entries)} bytes={OUT.stat().st_size}")


if __name__ == "__main__":
    main()
