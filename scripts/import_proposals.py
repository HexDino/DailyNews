#!/usr/bin/env python3
"""Import Slow Reads link proposals into the queue.

Grok Bot runs in its own sandbox: it writes proposals to
/workspace/newspaper/slow-reads-proposals/<date>.json, which is not reachable
from this machine, and the publish automation reads slow-reads/queue.json. This
script is the bridge — drop Grok's JSON into .cache/proposals/ and the next
automation run picks it up.

Everything is re-checked here, because a proposal is a suggestion, not a
decision:
  - the domain must be in slow-reads/rights_allowlist.json
  - the URL and title must not already be in the library or the queue
  - quality_score must clear --min-quality
  - at most --max items, one per source, one per author

Usage:
  python scripts/import_proposals.py .cache/proposals/2026-10-30.json
  python scripts/import_proposals.py --dir .cache/proposals
  pbpaste | python scripts/import_proposals.py -        # pasted JSON from chat
  python scripts/import_proposals.py --dir .cache/proposals --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from discover_rss import canonical_url, load_json, normalize_title
from rights_gate import domain_of, find_entry, load_allowlist

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "slow-reads" / "queue.json"
INDEX = ROOT / "slow-reads" / "articles" / "index.json"
ALLOWLIST = ROOT / "slow-reads" / "rights_allowlist.json"
PROPOSAL_DIR = ROOT / ".cache" / "proposals"


def seen_sets() -> tuple[set[str], set[str]]:
    urls: set[str] = set()
    titles: set[str] = set()
    for article in load_json(INDEX, {}).get("articles") or []:
        if article.get("source_url"):
            urls.add(canonical_url(article["source_url"]))
        for key in ("title", "title_original"):
            if article.get(key):
                titles.add(normalize_title(article[key]))
    for item in load_json(QUEUE, {}).get("items") or []:
        if item.get("url"):
            urls.add(canonical_url(item["url"]))
        if item.get("title"):
            titles.add(normalize_title(item["title"]))
    return urls, titles


def normalise_payload(raw: object) -> list[dict]:
    """Accept a bare array, or an object with items/proposals/candidates."""
    if isinstance(raw, list):
        return [r for r in raw if isinstance(r, dict)]
    if isinstance(raw, dict):
        for key in ("items", "proposals", "candidates", "results"):
            value = raw.get(key)
            if isinstance(value, list):
                return [r for r in value if isinstance(r, dict)]
    raise ValueError("expected a JSON array of proposals")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    parser = argparse.ArgumentParser(description="Import Slow Reads proposals.")
    parser.add_argument("files", nargs="*", help="proposal JSON files, or - for stdin")
    parser.add_argument("--dir", type=Path, help="import every *.json in this directory")
    parser.add_argument("--min-quality", type=int, default=75)
    parser.add_argument("--max", type=int, default=5, help="max items to add per run")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    paths: list[Path] = [Path(f) for f in args.files if f != "-"]
    use_stdin = "-" in args.files
    if args.dir:
        if not args.dir.is_dir():
            print(f"ERROR {args.dir}: not a directory", file=sys.stderr)
            return 1
        paths.extend(sorted(args.dir.glob("*.json")))
    if not paths and not use_stdin:
        if PROPOSAL_DIR.is_dir():
            paths = sorted(PROPOSAL_DIR.glob("*.json"))
        if not paths:
            # Nothing to import is not a failure — the automation calls this
            # before every run, and most runs will have no proposals waiting.
            print(f"No proposal files in {PROPOSAL_DIR}. Nothing to import.")
            return 0

    allowlist = load_allowlist(ALLOWLIST)
    seen_urls, seen_titles = seen_sets()
    queue = load_json(QUEUE, {"version": 1, "rights_policy": "user-accepted", "items": []})
    items: list[dict] = queue.setdefault("items", [])

    proposals: list[dict] = []
    for path in paths:
        try:
            proposals.extend(normalise_payload(json.loads(path.read_text(encoding="utf-8"))))
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"ERROR {path}: {exc}", file=sys.stderr)
    if use_stdin:
        try:
            proposals.extend(normalise_payload(json.load(sys.stdin)))
        except (json.JSONDecodeError, ValueError) as exc:
            print(f"ERROR stdin: {exc}", file=sys.stderr)

    if not proposals:
        print("Proposal files contained no items. Nothing to import.")
        return 0

    added = 0
    skipped = 0
    per_source: dict[str, int] = {}
    per_author: dict[str, int] = {}

    for prop in proposals:
        url = str(prop.get("url") or "").strip()
        title = str(prop.get("title") or "").strip()
        source_id = str(prop.get("source_id") or prop.get("source") or "").strip()
        author = str(prop.get("author") or "").strip()

        if not url.startswith("http") or not title:
            print(f"SKIP (no url/title): {title[:50] or url[:50]}")
            skipped += 1
            continue

        domain = domain_of(url)
        entry = find_entry(allowlist, url, domain)
        if entry is None:
            print(f"SKIP (domain not allowlisted): {domain}")
            skipped += 1
            continue

        quality = prop.get("quality_score")
        if isinstance(quality, int) and quality < args.min_quality:
            print(f"SKIP (quality {quality} < {args.min_quality}): {title[:50]}")
            skipped += 1
            continue

        if canonical_url(url) in seen_urls or normalize_title(title) in seen_titles:
            print(f"SKIP (already known): {title[:60]}")
            skipped += 1
            continue

        if per_source.get(source_id, 0) >= 1:
            print(f"SKIP (second item from {source_id}): {title[:50]}")
            skipped += 1
            continue
        if author and per_author.get(author.lower(), 0) >= 1:
            print(f"SKIP (second item from {author}): {title[:50]}")
            skipped += 1
            continue
        if added >= args.max:
            print(f"SKIP (hit --max {args.max}): {title[:50]}")
            skipped += 1
            continue

        items.append(
            {
                "source_id": source_id or domain,
                "url": url,
                "title": title,
                "author": author,
                "source": str(prop.get("source") or entry.get("domain") or domain),
                "lang": str(prop.get("lang") or "en"),
                "topics_guess": prop.get("topics_guess") or [],
                "quality_score": quality if isinstance(quality, int) else 0,
                "quality_reason": str(prop.get("quality_reason") or ""),
                "est_words": prop.get("est_words") if isinstance(prop.get("est_words"), int) else 0,
                "fetch": str(prop.get("fetch") or "static"),
                "status": "candidate",
                "rights_note": "user-accepted",
                "added_at": date.today().isoformat(),
                "note": f"imported from Grok proposals; allowlist mode={entry.get('mode')}",
            }
        )
        seen_urls.add(canonical_url(url))
        seen_titles.add(normalize_title(title))
        per_source[source_id] = per_source.get(source_id, 0) + 1
        if author:
            per_author[author.lower()] = per_author.get(author.lower(), 0) + 1
        added += 1
        print(f"ADD  {title[:60]}  [{domain}, mode={entry.get('mode')}]")

    if args.dry_run:
        print(f"\nDry run: would add {added}, skip {skipped}.")
        return 0

    if added:
        QUEUE.write_text(
            json.dumps(queue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(f"\n{added} added to queue, {skipped} skipped.")
    # Adding nothing is normal: everything proposed may already be known.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
