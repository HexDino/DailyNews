#!/usr/bin/env python3
"""List public-domain Slow Reads candidates from slow-reads/public-domain.json.

Project Gutenberg's own feeds list whatever was uploaded this week, which has
nothing to do with the eight Slow Reads topics. This script reads the curated
catalogue instead: real works, verified ebook numbers, tagged by topic and
annotated with a length estimate so you do not start a 500,000-word book by
accident.

Output matches `discover_rss.py` candidates, plus `gutenberg_id`, `est_words`,
`title_original` and `suggested_id`, so the translate/publish steps stay the
same.

Usage:
  python scripts/discover_pd.py
  python scripts/discover_pd.py --topics Stoicism --max-words 40000
  python scripts/discover_pd.py --limit 5 --out .cache/pd-candidates.json --pretty
  python scripts/discover_pd.py --table
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from discover_rss import canonical_url, load_json, normalize_title

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "slow-reads" / "public-domain.json"
INDEX = ROOT / "slow-reads" / "articles" / "index.json"
QUEUE = ROOT / "slow-reads" / "queue.json"
SOURCE_ID = "project-gutenberg"
SOURCE_NAME = "Project Gutenberg"
DEFAULT_MAX_WORDS = 80000
DEFAULT_URL_TEMPLATE = "https://www.gutenberg.org/cache/epub/{id}/pg{id}-images.html"


def load_seen() -> tuple[set[str], set[str]]:
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()
    for article in load_json(INDEX, {}).get("articles") or []:
        if article.get("source_url"):
            seen_urls.add(canonical_url(article["source_url"]))
        for key in ("title", "title_original"):
            if article.get(key):
                seen_titles.add(normalize_title(article[key]))
    for item in load_json(QUEUE, {}).get("items") or []:
        if item.get("url"):
            seen_urls.add(canonical_url(item["url"]))
        if item.get("title"):
            seen_titles.add(normalize_title(item["title"]))
    return seen_urls, seen_titles


def build_candidates(args: argparse.Namespace, catalog_path: Path) -> list[dict]:
    catalog = load_json(catalog_path, None)
    if catalog is None:
        raise SystemExit(f"{catalog_path}: not found")
    template = catalog.get("url_template") or DEFAULT_URL_TEMPLATE
    seen_urls, seen_titles = load_seen()
    wanted = {t.strip().lower() for t in (args.topics or []) if t.strip()}
    excluded = {e.strip().lower() for e in (args.exclude_era or []) if e.strip()}
    only = {e.strip().lower() for e in (args.era or []) if e.strip()}

    picked: list[dict] = []
    for work in catalog.get("works") or []:
        gid = work.get("gutenberg_id")
        if not isinstance(gid, int):
            continue
        era = str(work.get("era") or "19c").lower()
        if excluded and era in excluded:
            continue
        if only and era not in only:
            continue
        words = work.get("est_words") or 0
        if args.max_words and words > args.max_words:
            continue
        topics = work.get("topics") or []
        if wanted and not (wanted & {t.lower() for t in topics}):
            continue
        url = template.format(id=gid)
        title = work.get("title_original") or ""
        if canonical_url(url) in seen_urls or normalize_title(title) in seen_titles:
            continue
        picked.append(
            {
                "source_id": SOURCE_ID,
                "source": SOURCE_NAME,
                "url": url,
                "title": title,
                "title_original": title,
                "author": work.get("author") or "",
                "published": None,
                "summary": work.get("note") or "",
                "topics": topics,
                "lang": work.get("lang") or "en",
                "quality": 95,
                "fetch": "static",
                "feed_mode": "catalog",
                "gutenberg_id": gid,
                "est_words": words,
                "era": era,
                "suggested_id": work.get("id") or "",
            }
        )

    # Contemporary work first, then length: a reader who asked for modern topics
    # should not get Plato just because Plato is short.
    era_rank = {"modern": 0, "19c": 1, "classical": 2}
    picked.sort(key=lambda c: (era_rank.get(c["era"], 1), c["est_words"] or 0, c["title"]))
    if not args.no_diversify:
        # Interleave inside each era tier, then concatenate: topic spread must
        # not pull a 19th-century title above a modern one.
        tiers: dict[str, list[dict]] = {}
        for candidate in picked:
            tiers.setdefault(candidate["era"], []).append(candidate)
        picked = []
        for era in sorted(tiers, key=lambda e: era_rank.get(e, 1)):
            picked.extend(interleave_topics(tiers[era]))
    return picked[: args.limit]


def interleave_topics(candidates: list[dict]) -> list[dict]:
    """Round-robin across topics so one subject cannot fill the whole batch."""
    groups: dict[str, list[dict]] = {}
    for candidate in candidates:
        key = (candidate.get("topics") or ["?"])[0]
        groups.setdefault(key, []).append(candidate)
    order = sorted(groups, key=lambda k: len(groups[k]), reverse=True)
    result: list[dict] = []
    index = 0
    while True:
        added = False
        for key in order:
            if index < len(groups[key]):
                result.append(groups[key][index])
                added = True
        if not added:
            break
        index += 1
    return result


def print_table(candidates: list[dict]) -> None:
    if not candidates:
        print("No public-domain candidates left for this filter.")
        return
    for candidate in candidates:
        topics = ", ".join(candidate.get("topics") or [])
        print(
            f"{candidate['est_words']:>7,}w {candidate.get('era','?')[:4]:<5} {candidate['suggested_id']:<32} "
            f"{candidate['title'][:46]:<46} | {topics}"
        )
        print(f"          {candidate['url']}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(
        description="List public-domain Slow Reads candidates from the catalogue."
    )
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--topics", help="comma-separated topic filter")
    parser.add_argument(
        "--max-words",
        type=int,
        default=DEFAULT_MAX_WORDS,
        help=f"skip works above this length (default {DEFAULT_MAX_WORDS}; 0 = no limit)",
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--out", type=Path, help="write JSON here instead of stdout")
    parser.add_argument("--pretty", action="store_true", help="indent JSON output")
    parser.add_argument(
        "--exclude-era",
        help="comma-separated eras to skip: classical, 19c, modern",
    )
    parser.add_argument("--era", help="only these eras: classical, 19c, modern")
    parser.add_argument("--no-diversify", action="store_true", help="keep length order")
    parser.add_argument("--table", action="store_true", help="human-readable table")
    args = parser.parse_args()

    if args.topics:
        args.topics = [t for t in args.topics.split(",") if t.strip()]
    if args.exclude_era:
        args.exclude_era = [e for e in args.exclude_era.split(",") if e.strip()]
    if args.era:
        args.era = [e for e in args.era.split(",") if e.strip()]

    candidates = build_candidates(args, args.catalog)

    if args.table:
        print_table(candidates)
        return 0

    payload = json.dumps(
        candidates, ensure_ascii=False, indent=2 if args.pretty else None
    )
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload + "\n", encoding="utf-8")
        print(f"Wrote {args.out} ({len(candidates)} candidates)", file=sys.stderr)
    else:
        print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
