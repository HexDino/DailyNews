#!/usr/bin/env python3
"""Rebuild doc-cham/articles/index.json from per-article JSON files.

Drop a new article as doc-cham/articles/<id>.json (see docs/DOC_CHAM_SCHEMA.md),
then run:

    python3 scripts/add_doc_cham.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARTICLES_DIR = ROOT / "doc-cham" / "articles"
INDEX_PATH = ARTICLES_DIR / "index.json"

# Canonical topic order for chips; extras from files are appended alphabetically.
CANONICAL_TOPICS = [
    "Con người",
    "Tình yêu",
    "Sự nghiệp",
    "Đối nhân xử thế",
    "Tiền bạc",
    "Tâm lý",
    "Tư duy & khoa học",
    "Stoicism",
]

INDEX_FIELDS = (
    "id",
    "title",
    "title_original",
    "author",
    "source",
    "source_url",
    "lang",
    "topics",
    "summary",
    "added",
    "reading_minutes",
)


def load_article(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path.name}: root must be an object")
    aid = data.get("id") or path.stem
    if path.stem != aid:
        raise ValueError(f"{path.name}: id {aid!r} must match filename stem {path.stem!r}")
    if not data.get("title"):
        raise ValueError(f"{path.name}: missing title")
    if not isinstance(data.get("body"), list) or not data["body"]:
        raise ValueError(f"{path.name}: body must be a non-empty array")
    topics = data.get("topics") or []
    if not isinstance(topics, list):
        raise ValueError(f"{path.name}: topics must be an array")
    entry = {k: data.get(k) for k in INDEX_FIELDS}
    entry["id"] = aid
    entry["title"] = data["title"]
    entry["title_original"] = data.get("title_original") or ""
    entry["author"] = data.get("author") or ""
    entry["source"] = data.get("source") or ""
    entry["source_url"] = data.get("source_url") or ""
    entry["lang"] = data.get("lang") or "vi"
    entry["topics"] = [str(t) for t in topics]
    entry["summary"] = data.get("summary") or ""
    entry["added"] = data.get("added") or ""
    mins = data.get("reading_minutes")
    entry["reading_minutes"] = int(mins) if mins is not None else 1
    return entry


def ordered_topics(entries: list[dict]) -> list[str]:
    seen: set[str] = set()
    for e in entries:
        for t in e.get("topics") or []:
            seen.add(t)
    ordered = [t for t in CANONICAL_TOPICS if t in seen]
    extras = sorted(t for t in seen if t not in CANONICAL_TOPICS)
    return ordered + extras


def rebuild() -> dict:
    paths = sorted(
        p for p in ARTICLES_DIR.glob("*.json") if p.name != "index.json"
    )
    if not paths:
        raise SystemExit(f"No article files in {ARTICLES_DIR}")
    entries = [load_article(p) for p in paths]
    entries.sort(key=lambda e: (e.get("added") or "", e["id"]), reverse=True)
    index = {
        "version": 1,
        "topics": ordered_topics(entries),
        "articles": entries,
    }
    ARTICLES_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_PATH.write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return index


def main() -> int:
    index = rebuild()
    print(
        f"Wrote {INDEX_PATH.relative_to(ROOT)} "
        f"({len(index['articles'])} articles, {len(index['topics'])} topics)"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        raise SystemExit(1)
