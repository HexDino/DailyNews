#!/usr/bin/env python3
"""Validate Slow Reads article JSON before publishing.

Usage:
  python scripts/validate_slow_read.py                    # check every article
  python scripts/validate_slow_read.py path/to/id.json    # check selected files
  python scripts/validate_slow_read.py --strict           # warnings are fatal (CI)

Checks schema (docs/SLOW_READS_SCHEMA.md), body blocks, index consistency and
translation coverage against the embedded source_stats (or the cached source
under .cache/slow-reads/ when available).

Exit codes: 0 ok, 1 validation failure.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

from source_stats import STATS_INT_FIELDS, compute_stats, count_sentences, find_source

ROOT = Path(__file__).resolve().parent.parent
ARTICLES_DIR = ROOT / "slow-reads" / "articles"
INDEX_PATH = ARTICLES_DIR / "index.json"
DEFAULT_CACHE = ROOT / ".cache" / "slow-reads"

ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
LANG_RE = re.compile(r"^[a-z]{2,3}(?:-[A-Za-z]{2,4})?$")
HTML_RE = re.compile(r"</?[a-zA-Z][^>]*>")

REQUIRED_FIELDS = (
    "id",
    "title",
    "author",
    "source",
    "lang",
    "topics",
    "summary",
    "added",
    "reading_minutes",
    "body",
)
OPTIONAL_FIELDS = {"title_original", "source_url", "source_stats"}
BLOCK_FIELDS = {
    "p": {"type", "text"},
    "h2": {"type", "text"},
    "h3": {"type", "text"},
    "quote": {"type", "text", "cite"},
}
EN_STOPWORDS = {
    "the", "and", "of", "to", "is", "that", "in", "it", "was", "for",
    "with", "as", "on", "be", "this", "from", "at", "by", "or", "an",
    "are", "were", "has", "have", "had", "not", "but", "they", "you",
}
WORDS_PER_MINUTE = 180
SHA_RE = re.compile(r"^[0-9a-f]{64}$")


def block_text(block: dict) -> str:
    return str(block.get("text") or "")


def body_text(blocks: list[dict]) -> str:
    return "\n".join(block_text(b) for b in blocks if isinstance(b, dict))


def compact_len(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def is_nonempty_str(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def check_blocks(blocks: object, errors: list[str], warnings: list[str]) -> None:
    if not isinstance(blocks, list) or not blocks:
        errors.append("body must be a non-empty array")
        return
    for i, block in enumerate(blocks):
        where = f"body[{i}]"
        if not isinstance(block, dict):
            errors.append(f"{where} must be an object")
            continue
        btype = block.get("type")
        if btype not in BLOCK_FIELDS:
            errors.append(f"{where}.type {btype!r} not in {sorted(BLOCK_FIELDS)}")
            continue
        if not is_nonempty_str(block.get("text")):
            errors.append(f"{where}.text must be a non-empty string")
            continue
        extra = set(block) - BLOCK_FIELDS[btype]
        if extra:
            warnings.append(f"{where} has unknown fields {sorted(extra)}")
        if btype == "quote" and "cite" in block and not isinstance(block["cite"], str):
            errors.append(f"{where}.cite must be a string")
        text = block_text(block)
        if HTML_RE.search(text):
            warnings.append(f"{where} contains HTML tags; use plain text")
        if btype == "p" and re.match(r"^\s*(#{1,6}\s|>\s)", text):
            warnings.append(f"{where} looks like Markdown; use h2/h3/quote blocks")


def english_residue(text: str) -> tuple[int, float]:
    tokens = re.findall(r"[a-zA-Z]+", text.lower())
    if not tokens:
        return 0, 0.0
    hits = sum(1 for t in tokens if t in EN_STOPWORDS)
    return hits, hits / len(tokens)


def check_source_stats(
    stats: object, errors: list[str], warnings: list[str]
) -> dict | None:
    if not isinstance(stats, dict):
        errors.append("source_stats must be an object")
        return None
    for field in STATS_INT_FIELDS:
        value = stats.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            errors.append(f"source_stats.{field} must be a non-negative integer")
    url = stats.get("url")
    if url is not None and (
        not isinstance(url, str) or not url.startswith(("http://", "https://"))
    ):
        warnings.append("source_stats.url should be an http(s) URL")
    sha = stats.get("sha256")
    if not isinstance(sha, str) or not SHA_RE.match(sha):
        errors.append("source_stats.sha256 must be 64 lowercase hex chars")
    coverage = stats.get("coverage")
    if coverage is not None and coverage not in ("full", "condensed"):
        errors.append("source_stats.coverage must be 'full' or 'condensed'")
    word_count = stats.get("word_count")
    if (
        isinstance(word_count, int)
        and not isinstance(word_count, bool)
        and word_count < 50
    ):
        warnings.append("source_stats.word_count is very small; check the fetched source")
    return stats


def coverage_messages(
    stats: dict, blocks: list[dict], warnings: list[str], notes: list[str]
) -> None:
    strict = (stats.get("coverage") or "full") == "full"
    src_chars = stats.get("char_count") or 0
    if not isinstance(src_chars, int) or src_chars < 200:
        return
    text = body_text(blocks)
    char_ratio = compact_len(text) / src_chars
    if char_ratio < 0.45:
        message = (
            f"translation is {char_ratio:.0%} of source length; check for skipped sections"
        )
        (warnings if strict else notes).append(message)
    elif char_ratio > 3.0:
        message = (
            f"translation is {char_ratio:.1f}x source length; check for added content"
        )
        (warnings if strict else notes).append(message)

    src_paragraphs = stats.get("paragraph_count") or 0
    block_ratio = len(blocks) / src_paragraphs if src_paragraphs else 1.0
    if src_paragraphs and block_ratio < 0.5:
        notes.append(f"only {len(blocks)} blocks vs {src_paragraphs} source paragraphs")

    src_sentences = stats.get("sentence_count") or 0
    body_sentences = count_sentences(text)
    sentence_ratio = body_sentences / src_sentences if src_sentences else 1.0
    if src_sentences and sentence_ratio < 0.5:
        message = f"only {body_sentences} sentences vs {src_sentences} in source"
        (warnings if strict else notes).append(message)

    src_headings = stats.get("heading_count") or 0
    body_headings = sum(1 for b in blocks if b.get("type") in ("h2", "h3"))
    if src_headings and body_headings < src_headings:
        notes.append(f"only {body_headings} headings vs {src_headings} in source")

    notes.append(
        f"coverage: chars {char_ratio:.0%}, blocks {block_ratio:.0%}, "
        f"sentences {sentence_ratio:.0%}"
    )


def validate_article(
    path: Path,
    cache_dir: Path | None,
    today: date,
    errors: list[str],
    warnings: list[str],
    notes: list[str],
) -> str | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"invalid JSON: {exc}")
        return None
    except OSError as exc:
        errors.append(f"cannot read file: {exc}")
        return None
    if not isinstance(data, dict):
        errors.append("root must be an object")
        return None

    for field in REQUIRED_FIELDS:
        value = data.get(field)
        if value is None or value == "" or value == []:
            errors.append(f"missing or empty field {field!r}")
    for field in ("title", "author", "source", "summary"):
        if field in data and not is_nonempty_str(data.get(field)):
            errors.append(f"{field} must be a non-empty string")

    aid = data.get("id")
    if is_nonempty_str(aid):
        if not ID_RE.match(aid):
            errors.append(f"id {aid!r} must match [a-z0-9-]+")
        if path.stem != aid:
            errors.append(f"id {aid!r} must match filename stem {path.stem!r}")
    else:
        aid = None

    unknown = set(data) - set(REQUIRED_FIELDS) - OPTIONAL_FIELDS
    if unknown:
        warnings.append(f"unknown top-level fields {sorted(unknown)}")

    lang = data.get("lang")
    if lang is not None and not is_nonempty_str(lang):
        errors.append("lang must be a non-empty string")
    elif is_nonempty_str(lang) and not LANG_RE.match(lang):
        warnings.append(f"lang {lang!r} does not look like a language code")

    title_original = data.get("title_original")
    if title_original is not None and not isinstance(title_original, str):
        errors.append("title_original must be a string")
    if is_nonempty_str(lang) and lang != "vi" and not is_nonempty_str(title_original):
        warnings.append("translated article should keep title_original")

    source_url = data.get("source_url")
    if source_url is not None and not isinstance(source_url, str):
        errors.append("source_url must be a string")
    elif is_nonempty_str(source_url) and not source_url.startswith(("http://", "https://")):
        errors.append("source_url must start with http:// or https://")
    elif is_nonempty_str(lang) and lang != "vi" and not is_nonempty_str(source_url):
        warnings.append("translated article should keep source_url")

    topics = data.get("topics")
    if topics is not None:
        if not isinstance(topics, list) or not topics:
            errors.append("topics must be a non-empty array")
        elif not all(is_nonempty_str(t) for t in topics):
            errors.append("topics entries must be non-empty strings")

    summary = data.get("summary")
    if isinstance(summary, str) and len(summary) > 400:
        notes.append(f"summary is {len(summary)} chars; keep it 1-2 sentences")

    added = data.get("added")
    if is_nonempty_str(added):
        try:
            added_date = datetime.strptime(added, "%Y-%m-%d").date()
            if added_date > today + timedelta(days=1):
                warnings.append(f"added {added} is in the future")
        except ValueError:
            errors.append("added must be YYYY-MM-DD")

    minutes = data.get("reading_minutes")
    if minutes is not None:
        if isinstance(minutes, bool) or not isinstance(minutes, int) or minutes < 1:
            errors.append("reading_minutes must be an integer >= 1")

    blocks = data.get("body")
    check_blocks(blocks, errors, warnings)
    if not isinstance(blocks, list):
        return aid
    blocks = [b for b in blocks if isinstance(b, dict)]

    if compact_len(body_text(blocks)) < 200:
        errors.append("body is too short to be a full article (<200 chars)")

    if is_nonempty_str(lang) and lang != "vi":
        hits, ratio = english_residue(body_text(blocks))
        if hits >= 10 and ratio >= 0.06:
            warnings.append(
                f"{hits} English function words left ({ratio:.0%}); looks untranslated"
            )

    if isinstance(minutes, int) and not isinstance(minutes, bool):
        expected = max(1, round(len(body_text(blocks).split()) / WORDS_PER_MINUTE))
        if abs(minutes - expected) > max(2, round(expected * 0.4)):
            notes.append(f"reading_minutes={minutes} but body is ~{expected} min")

    embedded_stats: dict | None = None
    if data.get("source_stats") is None:
        warnings.append(
            f"missing source_stats; run scripts/attach_source_stats.py {aid or path.stem}"
        )
    else:
        embedded_stats = check_source_stats(data["source_stats"], errors, warnings)

    stats_for_coverage = embedded_stats
    if aid and cache_dir is not None and cache_dir.is_dir():
        src_path, meta_path = find_source(
            aid, source_url if is_nonempty_str(source_url) else None, cache_dir
        )
        if src_path is not None:
            live_stats = compute_stats(
                src_path.read_text(encoding="utf-8", errors="replace")
            )
            if embedded_stats:
                live_stats["coverage"] = embedded_stats.get("coverage") or "full"
                if embedded_stats.get("sha256") != live_stats["sha256"]:
                    warnings.append(
                        "source_stats.sha256 does not match cached source; rerun attach"
                    )
            stats_for_coverage = live_stats
        meta: object = None
        if meta_path is not None:
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                notes.append("source meta.json is unreadable")
        if isinstance(meta, dict):
            meta_url = str(meta.get("url") or "").rstrip("/")
            if is_nonempty_str(source_url) and meta_url and meta_url != source_url.rstrip("/"):
                warnings.append("source_url differs from fetched source url")
            meta_lang = str(meta.get("language") or "")[:2].lower()
            if meta_lang and is_nonempty_str(lang) and meta_lang != lang[:2].lower():
                notes.append(f"lang={lang} but source metadata says {meta_lang}")

    if isinstance(embedded_stats, dict):
        embedded_url = str(embedded_stats.get("url") or "").rstrip("/")
        if (
            is_nonempty_str(source_url)
            and embedded_url
            and embedded_url != source_url.rstrip("/")
        ):
            warnings.append("source_stats.url differs from source_url")

    if isinstance(stats_for_coverage, dict):
        coverage_messages(stats_for_coverage, blocks, warnings, notes)

    return aid


def load_index_ids() -> set[str] | None:
    if not INDEX_PATH.is_file():
        return None
    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return set()
    return {str(a.get("id")) for a in data.get("articles") or [] if a.get("id")}


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate Slow Reads article JSON.")
    parser.add_argument("paths", nargs="*", help="article JSON files (default: all)")
    parser.add_argument("--strict", action="store_true", help="treat warnings as failures")
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=DEFAULT_CACHE,
        help=f"fetched sources for coverage checks (default: {DEFAULT_CACHE})",
    )
    parser.add_argument("--no-cache", action="store_true", help="skip source coverage checks")
    args = parser.parse_args()

    paths = [Path(p) for p in args.paths] or sorted(
        p for p in ARTICLES_DIR.glob("*.json") if p.name != "index.json"
    )
    if not paths:
        print("No article files found.", file=sys.stderr)
        return 1

    today = date.today()
    cache_dir = args.cache_dir if not args.no_cache else None
    checked: set[str] = set()
    total_errors = 0
    total_warnings = 0
    total_notes = 0

    for path in paths:
        errors: list[str] = []
        warnings: list[str] = []
        notes: list[str] = []
        aid = validate_article(path, cache_dir, today, errors, warnings, notes)
        if aid:
            checked.add(aid)
        total_errors += len(errors)
        total_warnings += len(warnings)
        total_notes += len(notes)
        label = aid or path.stem
        if errors:
            print(f"ERROR {path.name}")
        elif warnings:
            print(f"WARN  {path.name}")
        else:
            print(f"OK    {path.name}")
        for msg in errors:
            print(f"  error: {msg}")
        for msg in warnings:
            print(f"  warn:  {msg}")
        for msg in notes:
            print(f"  note:  {msg}")

    index_ids = load_index_ids()
    if index_ids is not None:
        file_ids = {
            p.stem for p in ARTICLES_DIR.glob("*.json") if p.name != "index.json"
        }
        missing = sorted(checked - index_ids)
        extra = sorted(index_ids - file_ids)
        if missing:
            print(f"WARN  {len(missing)} validated article(s) missing from index.json: {missing}")
            total_warnings += len(missing)
        if extra:
            print(f"WARN  {len(extra)} index entr(ies) stale: {extra}")
            total_warnings += len(extra)

    print(
        f"\nChecked {len(paths)} file(s): "
        f"{total_errors} error(s), {total_warnings} warning(s), {total_notes} note(s)."
    )
    if total_errors or (args.strict and total_warnings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
