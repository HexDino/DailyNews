#!/usr/bin/env python3
"""Rebuild issues/index.json from issues/YYYY-MM-DD/content.json folders."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ISSUES = ROOT / "issues"


def main() -> None:
    dates = sorted(
        p.name
        for p in ISSUES.iterdir()
        if p.is_dir() and (p / "content.json").is_file()
    )
    if not dates:
        raise SystemExit("No issues found")
    index = {
        "masthead": "Daily News",
        "latest": dates[-1],
        "issues": [{"date": d, "path": f"{d}/content.json"} for d in dates],
    }
    (ISSUES / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Index updated: {len(dates)} issues, latest {dates[-1]}")


if __name__ == "__main__":
    main()
