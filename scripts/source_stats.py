#!/usr/bin/env python3
"""Shared source-text statistics for the Slow Reads pipeline.

`compute_stats` runs on the extracted source text (source.txt) so the article
can carry a compact, copyright-free record of how much text the translation
should cover. `find_source` locates a cached source by article id or source URL.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

STATS_INT_FIELDS = (
    "word_count",
    "char_count",
    "paragraph_count",
    "sentence_count",
    "heading_count",
)


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def count_sentences(text: str) -> int:
    clean = collapse_ws(text)
    if not clean:
        return 0
    parts = [s for s in re.split(r"(?<=[.!?\u2026])\s+", clean) if len(s.split()) >= 3]
    return len(parts) or 1


def count_headings(text: str) -> int:
    """Count section headings; the single-# title line is not a section."""
    return sum(
        1 for line in text.splitlines() if re.match(r"^#{2,6}\s+\S", line.strip())
    )


def compute_stats(text: str) -> dict[str, int | str]:
    clean = text.strip()
    return {
        "word_count": len(clean.split()),
        "char_count": len(re.sub(r"\s+", "", clean)),
        "paragraph_count": len(
            [p for p in re.split(r"\n\s*\n", clean) if p.strip()]
        ),
        "sentence_count": count_sentences(clean),
        "heading_count": count_headings(clean),
        "sha256": hashlib.sha256(clean.encode("utf-8")).hexdigest(),
    }


def find_source(
    aid: str, source_url: str | None, cache_dir: Path
) -> tuple[Path | None, Path | None]:
    """Return (source.txt, meta.json) for an article id or matching source URL."""
    source_path = cache_dir / aid / "source.txt"
    meta_path = cache_dir / aid / "meta.json"
    if source_path.is_file():
        return source_path, meta_path if meta_path.is_file() else None
    if not source_url:
        return None, None
    target = source_url.rstrip("/")
    for candidate in sorted(cache_dir.glob("*/meta.json")):
        try:
            meta = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if str(meta.get("url") or "").rstrip("/") == target:
            sibling = candidate.with_name("source.txt")
            if sibling.is_file():
                return sibling, candidate
    return None, None
