#!/usr/bin/env python3
"""Attach source_stats to Slow Reads article JSON so CI can check coverage.

Reads the cached source under .cache/slow-reads/ (matched by article id or
source_url), computes word/char/paragraph/sentence/heading counts plus a
SHA-256, and stores them under "source_stats" in the article JSON. Only the
numbers are committed, never the source text.

Usage:
  python scripts/attach_source_stats.py --all
  python scripts/attach_source_stats.py bai-viet-1 bai-viet-2

Run this after translating and before validate_slow_read.py. Requires the
source cache created by scripts/fetch_source.py.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from source_stats import compute_stats, count_sentences, find_source

ROOT = Path(__file__).resolve().parent.parent
ARTICLES_DIR = ROOT / "slow-reads" / "articles"
DEFAULT_CACHE = ROOT / ".cache" / "slow-reads"


def body_text(blocks: list[dict]) -> str:
    return "\n".join(
        str(block.get("text") or "")
        for block in blocks
        if isinstance(block, dict)
    )


def attach(path: Path, cache_dir: Path, coverage: str | None) -> tuple[bool, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    aid = data.get("id") or path.stem
    if path.stem != aid:
        raise ValueError(f"id {aid!r} must match filename stem {path.stem!r}")

    source_path, meta_path = find_source(aid, data.get("source_url"), cache_dir)
    if source_path is None:
        raise FileNotFoundError(f"no cached source for {aid}; run fetch_source.py first")

    stats = compute_stats(source_path.read_text(encoding="utf-8", errors="replace"))
    meta: dict = {}
    if meta_path is not None:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    existing = data.get("source_stats") or {}
    policy = coverage or existing.get("coverage") or "full"
    embedded = {
        "url": meta.get("url") or data.get("source_url") or "",
        "coverage": policy,
        **stats,
    }

    blocks = data.get("body") or []
    text = body_text(blocks)
    char_ratio = (
        len(re.sub(r"\s+", "", text)) / stats["char_count"]
        if stats["char_count"]
        else 0
    )
    block_ratio = (
        len(blocks) / stats["paragraph_count"] if stats["paragraph_count"] else 0
    )
    sent_ratio = (
        count_sentences(text) / stats["sentence_count"]
        if stats["sentence_count"]
        else 0
    )
    summary = (
        f"{policy}; source {stats['word_count']}w/{stats['paragraph_count']}p/"
        f"{stats['sentence_count']}s -> body {len(blocks)} blocks, "
        f"{count_sentences(text)}s "
        f"(chars {char_ratio:.0%}, blocks {block_ratio:.0%}, sentences {sent_ratio:.0%})"
    )

    if data.get("source_stats") == embedded:
        return False, summary

    ordered: dict = {}
    for key, value in data.items():
        if key == "source_stats":
            continue
        if key == "body":
            ordered["source_stats"] = embedded
        ordered[key] = value
    if "source_stats" not in ordered:
        ordered["source_stats"] = embedded

    path.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return True, summary


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Attach source_stats to Slow Reads article JSON."
    )
    parser.add_argument("ids", nargs="*", help="article ids (filename stems)")
    parser.add_argument("--all", action="store_true", help="process every article")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument(
        "--coverage",
        choices=("full", "condensed", "excerpt"),
        help="coverage policy to store (default: keep existing, else full)",
    )
    args = parser.parse_args()

    if args.ids and args.all:
        parser.error("pass ids or --all, not both")
    if not args.ids and not args.all:
        parser.error("pass at least one id or --all")

    if args.all:
        paths = sorted(
            p for p in ARTICLES_DIR.glob("*.json") if p.name != "index.json"
        )
    else:
        paths = [ARTICLES_DIR / f"{aid}.json" for aid in args.ids]

    failures = 0
    changed = 0
    for path in paths:
        if not path.is_file():
            print(f"ERROR {path.name}: article file not found", file=sys.stderr)
            failures += 1
            continue
        try:
            updated, summary = attach(path, args.cache_dir, args.coverage)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"ERROR {path.name}: {exc}", file=sys.stderr)
            failures += 1
            continue
        changed += int(updated)
        print(f"{'updated' if updated else 'unchanged'} {path.stem}: {summary}")

    print(f"\n{changed} updated, {len(paths) - failures} ok, {failures} failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
