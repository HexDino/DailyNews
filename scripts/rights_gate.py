#!/usr/bin/env python3
"""Licence gate for Slow Reads: block publishing that needs rights we do not have.

A Vietnamese translation of a protected article is a **derivative work**. Posting
it publicly needs a licence that permits derivative works. `rights_note:
"user-accepted"` in queue.json is a risk note, not a licence — this script
ignores it entirely and reads only slow-reads/rights_allowlist.json.

Policy
------
`coverage: "full"` or `"condensed"` requires an allowlist entry whose `basis`
permits derivative works:

    public-domain                      yes
    CC-BY, CC-BY-SA, CC-BY-4.0 …       yes (attribution; SA also share-alike)
    CC-BY-ND, CC-BY-NC, CC-BY-NC-ND    no  (ND/NC forbid the derivative)
    user-confirmed-permission          only with a non-empty `evidence` field
    excerpt-only                       no

`coverage: "excerpt"` only needs an allowlist entry (any mode); the article must
keep `source_url` so readers can reach the original.

`coverage: "summary"` is allowed for any allowlisted source, including
excerpt-only, because it carries ideas and facts in the writer's own words. Two
caps keep it from drifting into an abridged translation: 250-900 words, and at
most 30% of the source's length.

Severity
--------
error  hard violation — CI must fail (no entry, expired entry, basis forbids
       derivatives, or the article URL does not match the allowlisted domain)
warn   `user-confirmed-permission` with no `evidence` — passes CI but is printed
       loudly, because there is no document on file behind that claim

Usage
-----
  python scripts/rights_gate.py                     # every article
  python scripts/rights_gate.py path/to/id.json     # selected files
  python scripts/rights_gate.py --quiet             # only errors

Exit codes: 0 ok, 1 violation.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
ARTICLES_DIR = ROOT / "slow-reads" / "articles"
ALLOWLIST_PATH = ROOT / "slow-reads" / "rights_allowlist.json"

DERIVATIVE_MODES = ("full", "condensed")

# Mirrors validate_slow_read.py: a summary must stay a summary.
SUMMARY_MIN_WORDS = 250
SUMMARY_MAX_WORDS = 900
SUMMARY_MAX_RATIO = 0.30

# Bases that permit a published derivative work without further evidence.
PERMISSIVE_BASES = {"public-domain"}
# Bases that need a document on file before they count as permission.
EVIDENCE_REQUIRED_BASES = {"user-confirmed-permission"}


def domain_of(url: str) -> str:
    host = urlparse(url or "").netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _body_size(data: dict) -> tuple[int, int]:
    """Return (words, characters) of an article body."""
    text = " ".join(
        str(block.get("text") or "")
        for block in data.get("body") or []
        if isinstance(block, dict)
    )
    return len(text.split()), len(text)


def entry_matches(entry: dict, url: str, domain: str) -> bool:
    """Match `domain:x`, `url:...` and `path:...` entries against an article."""
    match = str(entry.get("match") or "").strip()
    if not match:
        return False
    kind, _, value = match.partition(":")
    value = value.strip()
    if kind == "domain":
        wanted = value.lower()
        if wanted.startswith("www."):
            wanted = wanted[4:]
        return domain == wanted or domain.endswith("." + wanted)
    if kind == "url":
        return url.rstrip("/") == value.rstrip("/")
    if kind == "path":
        return value in (urlparse(url).path or "")
    return False


def find_entry(allowlist: dict, url: str, domain: str) -> dict | None:
    for entry in allowlist.get("entries") or []:
        if entry_matches(entry, url, domain):
            return entry
    return None


def is_expired(entry: dict, today: date | None = None) -> bool:
    raw = entry.get("expires_at")
    if not raw:
        return False
    try:
        expiry = date.fromisoformat(str(raw)[:10])
    except ValueError:
        return False
    return expiry < (today or date.today())


def basis_verdict(entry: dict) -> tuple[str, str]:
    """Classify an allowlist entry as 'ok', 'warn' or 'blocked'."""
    basis = str(entry.get("basis") or "").strip()
    lowered = basis.lower()

    if lowered in PERMISSIVE_BASES:
        return "ok", basis
    if lowered.startswith("cc-by"):
        if "nd" in lowered or "nc" in lowered:
            return "blocked", f"{basis} forbids derivative works"
        return "ok", basis
    if lowered in EVIDENCE_REQUIRED_BASES:
        evidence = str(entry.get("evidence") or "").strip()
        if evidence:
            return "ok", f"{basis} (evidence: {evidence})"
        return "warn", "no document on file behind user-confirmed-permission"
    if lowered == "excerpt-only":
        return "blocked", "excerpt-only sources may not be translated in full"
    return "blocked", f"unknown basis {basis!r}"


def check_article(path: Path, allowlist: dict) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"cannot read article: {exc}"], warnings
    if not isinstance(data, dict):
        return ["root must be an object"], warnings

    url = str(data.get("source_url") or "").strip()
    if not url:
        return ["missing source_url; cannot resolve licence"], warnings
    domain = domain_of(url)
    stats = data.get("source_stats")
    coverage = "full"
    if isinstance(stats, dict):
        coverage = str(stats.get("coverage") or "full")
        stats_url = str(stats.get("url") or "").strip()
        if stats_url and domain_of(stats_url) != domain:
            errors.append(
                f"source_stats.url host {domain_of(stats_url)!r} does not match "
                f"source_url host {domain!r}"
            )

    entry = find_entry(allowlist, url, domain)
    if entry is None:
        default = str(allowlist.get("default") or "skip")
        errors.append(
            f"{domain or 'unknown domain'} is not in rights_allowlist.json "
            f"(default: {default})"
        )
        return errors, warnings

    if is_expired(entry):
        errors.append(
            f"allowlist entry {entry.get('match')!r} expired on {entry.get('expires_at')}"
        )
        return errors, warnings

    entry_domain = str(entry.get("domain") or "").lower()
    if entry_domain and entry_domain.startswith("www."):
        entry_domain = entry_domain[4:]
    if entry_domain and not (
        domain == entry_domain or domain.endswith("." + entry_domain)
    ):
        errors.append(
            f"article host {domain!r} does not match allowlisted host {entry_domain!r}"
        )

    mode = str(entry.get("mode") or "excerpt")
    if coverage in DERIVATIVE_MODES:
        verdict, reason = basis_verdict(entry)
        if verdict == "blocked":
            errors.append(
                f"coverage {coverage!r} needs a derivative licence, but "
                f"{entry.get('match')!r} has {reason}"
            )
        elif verdict == "warn":
            warnings.append(
                f"{entry.get('match')!r} claims {reason}; full translation "
                f"rests on an undocumented permission"
            )
        if mode == "excerpt":
            errors.append(
                f"coverage {coverage!r} contradicts allowlist mode 'excerpt' "
                f"for {entry.get('match')!r}; run make_excerpt.py"
            )
    elif coverage == "excerpt":
        if not data.get("source_url"):
            errors.append("excerpt must keep source_url so readers reach the original")
    elif coverage == "summary":
        # Allowed for any allowlisted source: a summary carries ideas and facts
        # in the writer's own words, not the original's expression. The caps
        # stop it from drifting into an abridged translation, which would need
        # the same licence as a full one.
        words, chars = _body_size(data)
        if not SUMMARY_MIN_WORDS <= words <= SUMMARY_MAX_WORDS:
            errors.append(
                f"summary must be {SUMMARY_MIN_WORDS}-{SUMMARY_MAX_WORDS} words, got {words}"
            )
        if not data.get("source_url"):
            errors.append("summary must keep source_url so readers reach the original")
        src_chars = stats.get("char_count") if isinstance(stats, dict) else 0
        if isinstance(src_chars, int) and src_chars >= 200:
            if chars / src_chars > SUMMARY_MAX_RATIO:
                errors.append(
                    f"summary is {chars / src_chars:.0%} of source length; must stay "
                    f"under {SUMMARY_MAX_RATIO:.0%} or it becomes an abridged translation"
                )
    else:
        errors.append(f"unknown coverage {coverage!r}")

    return errors, warnings


def load_allowlist(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_url(article_id: str, explicit: str | None = None) -> str:
    """Find the source URL for an article id: JSON, then cache meta, then queue."""
    if explicit:
        return explicit.strip()
    article = ARTICLES_DIR / f"{article_id}.json"
    if article.is_file():
        try:
            data = json.loads(article.read_text(encoding="utf-8"))
            url = str(data.get("source_url") or "").strip()
            if url:
                return url
        except (OSError, json.JSONDecodeError):
            pass
    meta = ROOT / ".cache" / "slow-reads" / article_id / "meta.json"
    if meta.is_file():
        try:
            url = str(json.loads(meta.read_text(encoding="utf-8")).get("url") or "")
            if url.strip():
                return url.strip()
        except (OSError, json.JSONDecodeError):
            pass
    queue_path = ROOT / "slow-reads" / "queue.json"
    if queue_path.is_file():
        try:
            queue = json.loads(queue_path.read_text(encoding="utf-8"))
            for item in queue.get("items") or []:
                if str(item.get("id") or "") == article_id and item.get("url"):
                    return str(item["url"]).strip()
        except (OSError, json.JSONDecodeError):
            pass
    return ""


def resolve_mode(article_id: str, allowlist: dict, url: str = "") -> str:
    """Return 'full', 'excerpt' or 'skip' for an article id."""
    resolved = resolve_url(article_id, url or None)
    if not resolved:
        return "skip"
    entry = find_entry(allowlist, resolved, domain_of(resolved))
    if entry is None:
        return "skip"
    return str(entry.get("mode") or "excerpt")


def main() -> int:
    parser = argparse.ArgumentParser(description="Enforce Slow Reads licence policy.")
    parser.add_argument("files", nargs="*", help="article JSON paths")
    parser.add_argument(
        "--allowlist", type=Path, default=ALLOWLIST_PATH, help="allowlist path"
    )
    parser.add_argument("--quiet", action="store_true", help="suppress warnings")
    parser.add_argument(
        "--mode",
        metavar="ID",
        help="print the allowlist mode (full|excerpt|skip) for an article id and exit",
    )
    parser.add_argument("--url", help="source URL when the cache has no meta.json")
    args = parser.parse_args()

    if not args.allowlist.is_file():
        print(f"ERROR allowlist not found: {args.allowlist}", file=sys.stderr)
        return 1
    allowlist = load_allowlist(args.allowlist)

    if args.mode:
        print(resolve_mode(args.mode, allowlist, args.url or ""))
        return 0

    if args.files:
        paths = [Path(f) for f in args.files]
    else:
        paths = sorted(p for p in ARTICLES_DIR.glob("*.json") if p.name != "index.json")

    total_errors = total_warnings = 0
    for path in paths:
        if not path.is_file():
            print(f"ERROR {path}: not found", file=sys.stderr)
            total_errors += 1
            continue
        errors, warnings = check_article(path, allowlist)
        if errors:
            print(f"ERROR {path.name}")
            for message in errors:
                print(f"  error: {message}")
        if warnings and not args.quiet:
            if not errors:
                print(f"WARN  {path.name}")
            for message in warnings:
                print(f"  warn:  {message}")
        total_errors += len(errors)
        total_warnings += len(warnings)

    checked = len(paths)
    print(
        f"\nChecked {checked} article(s): "
        f"{total_errors} error(s), {total_warnings} warning(s)."
    )
    return 1 if total_errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
