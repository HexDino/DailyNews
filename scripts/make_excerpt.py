#!/usr/bin/env python3
"""Convert Slow Reads articles to short excerpts according to allowlist mode.

Reads slow-reads/rights_allowlist.json. Articles whose source domain has
mode "excerpt" keep only the first 2-3 substantive paragraphs plus a link note;
full-text sources (mode "full") are untouched. The original JSON is backed up
under .cache/full-backup/ before conversion.

Author bios, publication notes and subscribe nags are skipped so the excerpt
budget goes to real prose. `--from-backup` re-cuts an existing excerpt from the
full text in .cache/full-backup/ without translating again.

Usage:
  python scripts/make_excerpt.py --all-excerpt --dry-run
  python scripts/make_excerpt.py --all-excerpt
  python scripts/make_excerpt.py --all-excerpt --from-backup
  python scripts/make_excerpt.py some-id other-id
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
ARTICLES = ROOT / "slow-reads" / "articles"
ALLOWLIST = ROOT / "slow-reads" / "rights_allowlist.json"
BACKUP = ROOT / ".cache" / "full-backup"
MAX_PARAGRAPHS = 3
MAX_CHARS = 1400
# Validator rejects excerpts above 1800 characters; never cross it to reach a
# second paragraph.
HARD_MAX_CHARS = 1800
MIN_PARA_CHARS = 120

# Openers that carry no content: author bios, publication notes, subscribe nags.
# Keeping them wastes the whole excerpt budget on boilerplate.
BOILERPLATE_MARKERS = (
    "là tổng biên tập",
    "là biên tập viên",
    "là cây bút",
    "đồng sáng lập",
    "là nhà báo",
    "là tác giả của cuốn",
    "bài viết này",
    "bài luận này",
    "bản dịch",
    "lược dịch",
    "đọc toàn bài",
    "trích đoạn",
    "đăng ký nhận",
    "nhận bản tin",
    "ảnh:",
    "nguồn:",
    "được đăng trên",
    "is the editor",
    "is a contributing",
    "is the author of",
    "this essay",
    "this article",
    "subscribe",
    "newsletter",
)


def is_boilerplate(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in BOILERPLATE_MARKERS)


def domain_of(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    return host[4:] if host.startswith("www.") else host


def load_modes() -> dict[str, dict]:
    data = json.loads(ALLOWLIST.read_text(encoding="utf-8"))
    return {
        str(entry.get("domain") or "").lower(): entry
        for entry in data.get("entries") or []
        if entry.get("domain")
    }


def _collect(
    blocks: list[dict],
    max_paragraphs: int,
    max_chars: int,
    min_chars: int,
    drop_boilerplate: bool,
) -> tuple[list[dict], int, int]:
    out: list[dict] = []
    paragraphs = 0
    chars = 0
    started = False
    for block in blocks:
        if not isinstance(block, dict):
            continue
        btype = block.get("type")
        text = str(block.get("text") or "").strip()
        if not text:
            continue
        if btype in ("h2", "h3"):
            # A leading heading is a useful opener; a heading further in means the
            # first section ended — skip it rather than stopping the excerpt there.
            if not started:
                out.append({"type": btype, "text": text})
            continue
        if paragraphs >= max_paragraphs:
            break
        # Skip content-free openers so the budget goes to real prose.
        if drop_boilerplate and (len(text) < min_chars or is_boilerplate(text)):
            continue
        # Always try for two paragraphs, but never past the validator's hard cap.
        if paragraphs >= 2 and chars + len(text) > max_chars:
            break
        if chars + len(text) > HARD_MAX_CHARS:
            break
        item = {"type": "quote" if btype == "quote" else "p", "text": text}
        if btype == "quote" and block.get("cite"):
            item["cite"] = block["cite"]
        out.append(item)
        paragraphs += 1
        chars += len(text)
        started = True
    return out, paragraphs, chars


def build_excerpt(
    blocks: list[dict], source_name: str, max_paragraphs: int, max_chars: int
) -> tuple[list[dict], int, int]:
    """Pick the opening prose, skipping bios and subscribe nags.

    Falls back to the raw first paragraphs when filtering leaves less than two,
    so a short or unusually formatted article still produces an excerpt.
    """
    out, paragraphs, chars = _collect(
        blocks, max_paragraphs, max_chars, MIN_PARA_CHARS, drop_boilerplate=True
    )
    if paragraphs < 2:
        out, paragraphs, chars = _collect(
            blocks, max_paragraphs, max_chars, 0, drop_boilerplate=False
        )
    if paragraphs == 0:
        return out, paragraphs, chars
    note = f"*Trích đoạn đầu bài — đọc toàn bài tại {source_name}.*"
    out.append({"type": "p", "text": note})
    return out, paragraphs, chars


def convert(path: Path, args: argparse.Namespace) -> tuple[str, str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    stats = data.get("source_stats")
    if not isinstance(stats, dict):
        raise ValueError("missing source_stats; run attach_source_stats.py first")
    already_excerpt = stats.get("coverage") == "excerpt"
    if already_excerpt and not args.from_backup:
        return "skip", "already excerpt (use --from-backup to re-cut it)"

    body = data.get("body") or []
    if args.from_backup:
        backup = BACKUP / path.name
        if not backup.is_file():
            raise ValueError(f"no full backup at {backup}")
        body = json.loads(backup.read_text(encoding="utf-8")).get("body") or []

    source_name = data.get("source") or domain_of(data.get("source_url") or "")
    excerpt, paragraphs, chars = build_excerpt(
        body, source_name, args.max_paragraphs, args.max_chars
    )
    if paragraphs == 0:
        raise ValueError("no paragraphs found")

    # Never back up an excerpt over the full text — the backup is the only copy.
    if not args.dry_run and not args.no_backup and not already_excerpt:
        BACKUP.mkdir(parents=True, exist_ok=True)
        backup = BACKUP / path.name
        if not backup.exists():
            shutil.copy2(path, backup)

    data["body"] = excerpt
    stats["coverage"] = "excerpt"
    words = len(" ".join(b["text"] for b in excerpt).split())
    data["reading_minutes"] = max(1, round(words / 180))
    if not args.dry_run:
        path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return "updated", f"{paragraphs} paragraphs, {chars} chars, {words} words"


def main() -> int:
    parser = argparse.ArgumentParser(description="Convert articles to excerpts.")
    parser.add_argument("ids", nargs="*", help="article ids (filename stems)")
    parser.add_argument(
        "--all-excerpt",
        action="store_true",
        help="convert every article whose allowlist mode is excerpt",
    )
    parser.add_argument("--max-paragraphs", type=int, default=MAX_PARAGRAPHS)
    parser.add_argument("--max-chars", type=int, default=MAX_CHARS)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-backup", action="store_true")
    parser.add_argument(
        "--from-backup",
        action="store_true",
        help="re-cut an existing excerpt from .cache/full-backup/<id>.json",
    )
    args = parser.parse_args()

    if args.ids and args.all_excerpt:
        parser.error("pass ids or --all-excerpt, not both")
    if not args.ids and not args.all_excerpt:
        parser.error("pass at least one id or --all-excerpt")

    modes = load_modes()
    if args.all_excerpt:
        paths = sorted(
            p for p in ARTICLES.glob("*.json") if p.name != "index.json"
        )
    else:
        paths = [ARTICLES / f"{aid}.json" for aid in args.ids]

    updated = skipped = failed = 0
    for path in paths:
        if not path.is_file():
            print(f"ERROR {path.name}: not found", file=sys.stderr)
            failed += 1
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        domain = domain_of(data.get("source_url") or "")
        entry = modes.get(domain)
        if args.all_excerpt:
            if not entry:
                print(f"SKIP {path.stem}: domain {domain or '?'} not in allowlist")
                skipped += 1
                continue
            if entry.get("mode") != "excerpt":
                print(f"SKIP {path.stem}: allowlist mode is {entry.get('mode')}")
                skipped += 1
                continue
        try:
            status, detail = convert(path, args)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            print(f"ERROR {path.stem}: {exc}", file=sys.stderr)
            failed += 1
            continue
        if status == "updated":
            updated += 1
            print(f"updated {path.stem}: {detail}")
        else:
            skipped += 1
            print(f"skip {path.stem}: {detail}")

    print(
        f"\n{updated} updated, {skipped} skipped, {failed} failed"
        + (" (dry run)" if args.dry_run else "")
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
