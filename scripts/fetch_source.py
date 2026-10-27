#!/usr/bin/env python3
"""Fetch a Slow Reads source page and cache its readable text for translation.

Downloads the page (or reads a saved HTML file), extracts the main article text
as Markdown, and writes:

    .cache/slow-reads/<id>/source.txt
    .cache/slow-reads/<id>/meta.json

The cache is local only (gitignored). Never commit source text: only the
translated article JSON goes into slow-reads/articles/.

Usage:
  python scripts/fetch_source.py https://example.com/essay --id song-ngan
  python scripts/fetch_source.py https://example.com/essay --html saved.html
  python scripts/fetch_source.py https://example.com/essay --force

Requires: pip install -r scripts/requirements.txt
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE = ROOT / ".cache" / "slow-reads"
USER_AGENT = (
    "Mozilla/5.0 (compatible; DailyNewsSlowReads/1.0; "
    "+https://hexdino.github.io/DailyNews/)"
)
ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def slugify(text: str) -> str:
    t = text.strip().lower().replace("đ", "d")
    t = unicodedata.normalize("NFD", t)
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return re.sub(r"-{2,}", "-", t)[:80].strip("-")


def id_from_url(url: str) -> str:
    path = urlparse(url).path.rstrip("/")
    stem = Path(path).stem if path else ""
    return slugify(stem) or slugify(urlparse(url).netloc) or "article"


def fetch_html(url: str, timeout: int) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read()
        charset = response.headers.get_content_charset() or "utf-8"
    for encoding in (charset, "utf-8", "utf-8-sig"):
        try:
            return raw.decode(encoding)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", errors="replace")


def normalize_text(text: str) -> str:
    text = re.sub(r"<sup>.*?</sup>", "", text, flags=re.S | re.I)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    return "\n\n".join(line for line in lines if line)


def collapse_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def paragraphize_if_needed(text: str, html: str) -> str:
    """Recover paragraphs on pages that separate them with <br><br>.

    trafilatura treats such pages as one block, which would hand the
    translator a single wall of text. Rebuild boundaries from <p> elements
    only when the extracted text has a very long block and the page uses
    repeated <br><br> separators, and accept the result only if the DOM
    candidates cover most of the extracted text.
    """
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if len(text) < 1500 or not any(len(p) >= 1500 for p in paragraphs):
        return text
    if len(re.findall(r"(?:<br\s*/?>\s*){2,}", html, flags=re.I)) < 3:
        return text
    from lxml import etree, html as lxml_html

    try:
        tree = lxml_html.fromstring(
            re.sub(r"(?:<br\s*/?>\s*){2,}", "</p><p>", html, flags=re.I)
        )
    except etree.ParserError:
        return text
    candidates: list[str] = []
    for node in tree.xpath("//p"):
        candidate = collapse_ws(node.text_content())
        if len(candidate) >= 60:
            candidates.append(candidate)
    clean = collapse_ws(text)
    if not clean or not candidates:
        return text
    parts: list[str] = []
    position = 0
    matched = 0
    for candidate in candidates:
        index = clean.find(candidate, position)
        if index == -1:
            continue
        gap = clean[position:index].strip()
        if gap:
            parts.append(gap)
        parts.append(candidate)
        matched += len(candidate)
        position = index + len(candidate)
    tail = clean[position:].strip()
    if tail:
        parts.append(tail)
    if matched / len(clean) < 0.6:
        return text
    return "\n\n".join(parts)


def extract(html: str, url: str, favor_recall: bool) -> tuple[str, object | None, str]:
    try:
        import trafilatura
    except ImportError:
        sys.exit(
            "Missing dependency. Run: pip install -r scripts/requirements.txt"
        )
    text = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_comments=False,
        include_tables=True,
        include_formatting=True,
        favor_recall=favor_recall,
    )
    meta = trafilatura.extract_metadata(html, default_url=url)
    version = getattr(trafilatura, "__version__", "?")
    return (text or "").strip(), meta, version


def meta_value(meta: object, name: str) -> str | None:
    value = getattr(meta, name, None)
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Fetch and cache a Slow Reads source.")
    parser.add_argument("url", help="article URL (used for metadata and cache id)")
    parser.add_argument("--id", help="cache/article slug (default: derived from URL)")
    parser.add_argument("--html", type=Path, help="extract from a saved HTML file instead of downloading")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--lang", help="override detected source language code")
    parser.add_argument("--keep-html", action="store_true", help="also save the raw HTML")
    parser.add_argument("--favor-recall", action="store_true", help="keep more text (may include boilerplate)")
    parser.add_argument("--force", action="store_true", help="overwrite an existing cached source")
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    aid = args.id or id_from_url(args.url)
    if not ID_RE.match(aid):
        parser.error(f"invalid id {aid!r}; use lowercase letters, digits and hyphens")

    out_dir = args.cache_dir / aid
    source_path = out_dir / "source.txt"
    if source_path.exists() and not args.force:
        print(f"Cache already exists: {source_path}", file=sys.stderr)
        print("Use --force to overwrite.", file=sys.stderr)
        return 3

    if args.html:
        try:
            html = args.html.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print(f"Cannot read {args.html}: {exc}", file=sys.stderr)
            return 4
        print(f"Read {args.html} ({len(html):,} chars)")
    else:
        try:
            html = fetch_html(args.url, args.timeout)
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
            print(f"Download failed: {exc}", file=sys.stderr)
            return 4
        print(f"Downloaded {len(html):,} chars from {args.url}")

    text, meta, version = extract(html, args.url, args.favor_recall)
    text = paragraphize_if_needed(normalize_text(text), html)
    if len(text) < 500:
        hint = "Save the page manually (browser: Save as HTML) and rerun with --html FILE."
        if not args.favor_recall:
            hint = "Try --favor-recall first, or " + hint[0].lower() + hint[1:]
        print(f"Extraction returned too little text. {hint}", file=sys.stderr)
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)
    source_path.write_text(text + "\n", encoding="utf-8")
    if args.keep_html:
        (out_dir / "source.html").write_text(html, encoding="utf-8")

    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    info = {
        "id": aid,
        "url": args.url,
        "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "title": meta_value(meta, "title"),
        "author": meta_value(meta, "author"),
        "date": meta_value(meta, "date"),
        "sitename": meta_value(meta, "sitename"),
        "language": args.lang or meta_value(meta, "language"),
        "word_count": len(text.split()),
        "char_count": len(text),
        "paragraph_count": len(paragraphs),
        "extractor": f"trafilatura {version}",
    }
    (out_dir / "meta.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    print(f"Wrote {source_path} ({info['word_count']:,} words, {len(paragraphs)} paragraphs)")
    print(f"Wrote {out_dir / 'meta.json'}")
    print(f"Source: {info['title'] or '(no title)'} — {info['sitename'] or args.url}")
    print("Next: translate source.txt into slow-reads/articles/<id>.json, then validate.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
