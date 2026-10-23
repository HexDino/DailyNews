#!/usr/bin/env python3
"""Rebuild issues/index.json from issues/YYYY-MM-DD/content.json folders."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ISSUES = ROOT / "issues"
SCRIPTS = ROOT / "scripts"

CHIEU_SUFFIX = "-chieu"
DOC_CHAM = "Đọc chậm"


def issue_sort_key(folder_name: str) -> tuple[str, int]:
    """Morning (plain date) before evening (-chieu) on the same calendar day."""
    if folder_name.endswith(CHIEU_SUFFIX):
        return (folder_name[: -len(CHIEU_SUFFIX)], 1)
    return (folder_name, 0)


def count_articles(data: dict) -> int:
    n = 0
    for sec in data.get("sections") or []:
        n += len(sec.get("items") or [])
    return n


def issue_edition(folder_name: str, data: dict) -> str:
    if folder_name.endswith(CHIEU_SUFFIX) or data.get("edition") == "chieu":
        return "chieu"
    return "sang"


def has_doc_cham_content(data: dict) -> bool:
    if DOC_CHAM in (data.get("topics") or []):
        return True
    for sec in data.get("sections") or []:
        if sec.get("topic") == DOC_CHAM:
            return True
        if DOC_CHAM in (sec.get("tags") or []):
            return True
        for item in sec.get("items") or []:
            if DOC_CHAM in (item.get("tags") or []):
                return True
    return False


def issue_entry(folder: Path) -> dict:
    data = json.loads((folder / "content.json").read_text(encoding="utf-8"))
    edition = issue_edition(folder.name, data)
    entry: dict = {
        "date": folder.name,
        "path": f"{folder.name}/content.json",
        "article_count": count_articles(data),
        "edition": edition,
    }
    if edition == "chieu":
        entry["edition_label"] = data.get("edition_label") or "Số buổi chiều"
    if has_doc_cham_content(data):
        entry["has_doc_cham"] = True
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
    subprocess.run(
        [sys.executable, str(SCRIPTS / "build_search_index.py")],
        check=True,
        cwd=str(ROOT),
    )


if __name__ == "__main__":
    main()
