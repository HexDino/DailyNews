#!/usr/bin/env python3
"""Rebuild issues/index.json from issues/YYYY-MM-DD/content.json folders."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ISSUES = ROOT / "issues"

CHIEU_SUFFIX = "-chieu"


def issue_sort_key(folder_name: str) -> tuple[str, int]:
    """Morning (plain date) before evening (-chieu) on the same calendar day."""
    if folder_name.endswith(CHIEU_SUFFIX):
        return (folder_name[: -len(CHIEU_SUFFIX)], 1)
    return (folder_name, 0)


def issue_entry(folder: Path) -> dict:
    data = json.loads((folder / "content.json").read_text(encoding="utf-8"))
    entry: dict = {"date": folder.name, "path": f"{folder.name}/content.json"}
    if data.get("edition"):
        entry["edition"] = data["edition"]
    if data.get("edition_label"):
        entry["edition_label"] = data["edition_label"]
    return entry


def main() -> None:
    folders = sorted(
        (
            p
            for p in ISSUES.iterdir()
            if p.is_dir() and (p / "content.json").is_file()
        ),
        key=lambda p: issue_sort_key(p.name),
    )
    if not folders:
        raise SystemExit("No issues found")
    issue_ids = [p.name for p in folders]
    index = {
        "masthead": "Daily News",
        "latest": issue_ids[-1],
        "issues": [issue_entry(p) for p in folders],
    }
    (ISSUES / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Index updated: {len(issue_ids)} issues, latest {issue_ids[-1]}")


if __name__ == "__main__":
    main()
