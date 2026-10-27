#!/usr/bin/env python3
"""List recent Slow Reads candidates from slow-reads/sources.json via RSS.

Only feed titles, links, dates and short excerpts are read. The script never
downloads or prints article bodies, so the discovery step stays metadata-only.

Usage:
  python scripts/discover_rss.py
  python scripts/discover_rss.py --sources aeon,psyche --limit 10 --days 60
  python scripts/discover_rss.py --out .cache/candidates.json --pretty

Feeds are cached under .cache/rss/ (gitignored). If a feed fails, a stale
cache is used with a warning; sources without RSS are skipped.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "slow-reads" / "sources.json"
INDEX = ROOT / "slow-reads" / "articles" / "index.json"
QUEUE = ROOT / "slow-reads" / "queue.json"
DEFAULT_CACHE = ROOT / ".cache" / "rss"
USER_AGENT = (
    "Mozilla/5.0 (compatible; DailyNewsSlowReads/1.0; "
    "+https://hexdino.github.io/DailyNews/)"
)
ATOM = "{http://www.w3.org/2005/Atom}"
DC_CREATOR = "{http://purl.org/dc/elements/1.1/}creator"
SUMMARY_MAX = 280
TRACKER_PARAMS = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid")


def load_json(path: Path, default: object) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as exc:
        raise SystemExit(f"{path}: invalid JSON: {exc}") from exc


def canonical_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith(TRACKER_PARAMS)
    ]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), path, urlencode(query), "")
    )


def normalize_title(title: str) -> str:
    text = unicodedata.normalize("NFD", html.unescape(title or ""))
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return " ".join(text.split())


def plain_text(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(value)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(text.split())


def short_text(value: str | None, limit: int = SUMMARY_MAX) -> str:
    text = plain_text(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    try:
        parsed = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        parsed = None
    if parsed is None:
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def read_feed(
    source: dict, cache_dir: Path, ttl_minutes: int, no_cache: bool
) -> tuple[bytes, str]:
    feed_url = source["rss"]
    cache_path = cache_dir / f"{source['id']}.xml"
    if cache_path.is_file() and not no_cache:
        age = time.time() - cache_path.stat().st_mtime
        if age < ttl_minutes * 60:
            return cache_path.read_bytes(), "cache"
    try:
        request = urllib.request.Request(
            feed_url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/rss+xml, application/xml, text/xml, */*",
            },
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(raw)
        return raw, "fetch"
    except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
        if cache_path.is_file():
            return cache_path.read_bytes(), f"stale ({exc})"
        raise RuntimeError(str(exc)) from exc


def parse_feed(raw: bytes, source: dict) -> list[dict]:
    root = ET.fromstring(raw)
    feed_url = source["rss"] or f"https://{source['domain']}/"
    entries: list[dict] = []

    if root.tag == "rss" or root.tag.endswith("rss"):
        channel = root.find("channel")
        if channel is None:
            return []
        for item in channel.findall("item"):
            link_el = item.find("link")
            link = (link_el.text or "").strip() if link_el is not None else ""
            if not link and link_el is not None:
                link = (link_el.get("href") or "").strip()
            if not link:
                guid = (item.findtext("guid") or "").strip()
                if guid.startswith(("http://", "https://")):
                    link = guid
            title = (item.findtext("title") or "").strip()
            author = (
                item.findtext(DC_CREATOR) or item.findtext("author") or ""
            ).strip()
            entries.append(
                {
                    "url": urljoin(feed_url, link),
                    "title": plain_text(title),
                    "author": plain_text(author),
                    "published": parse_date(item.findtext("pubDate")),
                    "summary": short_text(item.findtext("description")),
                }
            )
    elif root.tag == f"{ATOM}feed":
        for entry in root.findall(f"{ATOM}entry"):
            link = ""
            for link_el in entry.findall(f"{ATOM}link"):
                if link_el.get("rel") in (None, "", "alternate"):
                    link = (link_el.get("href") or "").strip()
                    if link:
                        break
            author_el = entry.find(f"{ATOM}author/{ATOM}name")
            entries.append(
                {
                    "url": urljoin(feed_url, link),
                    "title": plain_text(entry.findtext(f"{ATOM}title")),
                    "author": plain_text(
                        author_el.text if author_el is not None else ""
                    ),
                    "published": parse_date(
                        entry.findtext(f"{ATOM}published")
                        or entry.findtext(f"{ATOM}updated")
                    ),
                    "summary": short_text(
                        entry.findtext(f"{ATOM}summary")
                        or entry.findtext(f"{ATOM}content")
                    ),
                }
            )
    return entries


def load_seen() -> tuple[set[str], set[str]]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    index = load_json(INDEX, {})
    for article in index.get("articles") or []:
        url = article.get("source_url")
        if url:
            seen_urls.add(canonical_url(url))
        title = article.get("title")
        if title:
            seen_titles.add(normalize_title(title))
    queue = load_json(QUEUE, {})
    for item in queue.get("items") or []:
        url = item.get("url")
        if url:
            seen_urls.add(canonical_url(url))
        title = item.get("title")
        if title:
            seen_titles.add(normalize_title(title))
    return seen_urls, seen_titles


def interleave(candidates: list[dict]) -> list[dict]:
    """Round-robin across sources so one prolific feed cannot dominate."""
    groups: dict[str, list[dict]] = {}
    for candidate in candidates:
        groups.setdefault(candidate["source_id"], []).append(candidate)
    for group in groups.values():
        group.sort(key=lambda c: (c["quality"], c["published"] or ""), reverse=True)
    order = sorted(
        groups,
        key=lambda sid: (groups[sid][0]["quality"], groups[sid][0]["published"] or ""),
        reverse=True,
    )
    result: list[dict] = []
    round_index = 0
    while True:
        added = False
        for source_id in order:
            group = groups[source_id]
            if round_index < len(group):
                result.append(group[round_index])
                added = True
        if not added:
            break
        round_index += 1
    return result


def collect(
    sources: list[dict], args: argparse.Namespace
) -> tuple[list[dict], int, int, int, int]:
    seen_urls, seen_titles = load_seen()
    blocklist = [term.lower() for term in args.title_blocklist]
    cutoff = (
        datetime.now(timezone.utc) - timedelta(days=args.days) if args.days > 0 else None
    )
    candidates: list[dict] = []
    ok = failed = no_rss = blocked = 0

    for source in sources:
        if not source.get("rss"):
            no_rss += 1
            continue
        try:
            raw, mode = read_feed(
                source, args.cache_dir, args.cache_ttl, args.no_cache
            )
            entries = parse_feed(raw, source)
        except (RuntimeError, ET.ParseError, UnicodeError) as exc:
            failed += 1
            print(f"[fail] {source['id']}: {exc}", file=sys.stderr)
            continue
        ok += 1
        picked = 0
        for entry in entries:
            if picked >= args.per_source:
                break
            if not entry["url"] or not entry["title"]:
                continue
            if any(term in entry["title"].lower() for term in blocklist):
                blocked += 1
                continue
            published = entry["published"]
            if cutoff and published and published < cutoff:
                continue
            if cutoff and published is None and not args.allow_undated:
                continue
            url_key = canonical_url(entry["url"])
            title_key = normalize_title(entry["title"])
            if url_key in seen_urls or title_key in seen_titles:
                continue
            seen_urls.add(url_key)
            seen_titles.add(title_key)
            candidates.append(
                {
                    "source_id": source["id"],
                    "source": source["name"],
                    "url": entry["url"],
                    "title": entry["title"],
                    "author": entry["author"],
                    "published": published.isoformat() if published else None,
                    "summary": entry["summary"],
                    "topics": source.get("topics") or [],
                    "lang": source.get("lang") or "",
                    "quality": source.get("quality") or 75,
                    "fetch": source.get("fetch") or "static",
                    "feed_mode": mode,
                }
            )
            picked += 1

    candidates.sort(
        key=lambda c: (c["quality"], c["published"] or ""), reverse=True
    )
    if not args.no_diversify:
        candidates = interleave(candidates)
    return candidates[: args.limit], ok, failed, no_rss, blocked


def main() -> int:
    parser = argparse.ArgumentParser(
        description="List Slow Reads candidates from RSS feeds."
    )
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--sources", help="comma-separated source ids")
    parser.add_argument("--limit", type=int, default=30, help="max candidates")
    parser.add_argument("--per-source", type=int, default=5, help="max per feed")
    parser.add_argument("--days", type=int, default=60, help="recency window; 0 = all")
    parser.add_argument(
        "--min-quality", type=int, default=75, help="skip sources below this score"
    )
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument(
        "--cache-ttl", type=int, default=60, help="feed cache TTL in minutes"
    )
    parser.add_argument("--no-cache", action="store_true", help="always refetch")
    parser.add_argument(
        "--allow-undated", action="store_true", help="keep items without a date"
    )
    parser.add_argument(
        "--no-diversify",
        action="store_true",
        help="sort by quality/date only instead of round-robin across sources",
    )
    parser.add_argument(
        "--no-blocklist",
        action="store_true",
        help="keep titles that match the registry title_blocklist",
    )
    parser.add_argument("--out", type=Path, help="write JSON here instead of stdout")
    parser.add_argument("--pretty", action="store_true", help="indent JSON output")
    args = parser.parse_args()

    registry = load_json(args.registry, None)
    if not isinstance(registry, dict):
        print(f"Registry not found or invalid: {args.registry}", file=sys.stderr)
        return 1
    sources = registry.get("sources") or []
    if args.sources:
        wanted = {sid.strip() for sid in args.sources.split(",") if sid.strip()}
        known = {s.get("id") for s in sources}
        unknown = sorted(wanted - known)
        if unknown:
            parser.error(f"unknown source id(s): {', '.join(unknown)}")
        sources = [s for s in sources if s.get("id") in wanted]
    sources = [
        s for s in sources if (s.get("quality") or 0) >= args.min_quality
    ]
    args.title_blocklist = (
        [] if args.no_blocklist else registry.get("title_blocklist") or []
    )

    candidates, ok, failed, no_rss, blocked = collect(sources, args)
    payload = json.dumps(
        candidates, ensure_ascii=False, indent=2 if args.pretty else None
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
        print(f"Wrote {args.out} ({len(candidates)} candidates)", file=sys.stderr)
    else:
        print(payload)

    print(
        f"[discover] {ok} feed(s) ok, {failed} failed, {no_rss} without RSS, "
        f"{blocked} blocked by title, {len(candidates)} candidate(s)",
        file=sys.stderr,
    )
    return 0 if ok or not sources else 1


if __name__ == "__main__":
    raise SystemExit(main())
