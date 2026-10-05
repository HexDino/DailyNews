#!/usr/bin/env python3
"""Copy uploaded issue JSON/PDF into issues/ and normalize Daily News branding."""
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UPLOADS = Path("/home/ubuntu/.cursor/projects/workspace/uploads")
ISSUES = ROOT / "issues"

SECTION_TAGS = {
    "Trí tuệ nhân tạo": "ai",
    "Kho GitHub đáng chú ý": "github",
    "Bóng đá": "football",
    "Chính trị": "politics",
    "Văn hoá": "culture",
    "Đời sống": "lifestyle",
}

MASTHEAD = "Daily News"


def normalize(data: dict) -> dict:
    data = dict(data)
    data["masthead"] = MASTHEAD
    if data.get("tagline"):
        data["tagline"] = (
            data["tagline"]
            .replace("Báo Sáng của Hưng", MASTHEAD)
        )
    sections = []
    for sec in data.get("sections", []):
        sec = dict(sec)
        title = sec.get("title", "")
        sec["tags"] = sec.get("tags") or ([SECTION_TAGS[title]] if title in SECTION_TAGS else [])
        items = []
        for it in sec.get("items", []):
            it = dict(it)
            if "tags" not in it and sec["tags"]:
                it["tags"] = list(sec["tags"])
            items.append(it)
        sec["items"] = items
        sections.append(sec)
    data["sections"] = sections
    return data


def main() -> None:
    ISSUES.mkdir(parents=True, exist_ok=True)
    dates = []
    for day in range(1, 6):
        iso = f"2026-10-{day:02d}"
        json_src = UPLOADS / f"{iso}_aaa1.json"
        # uploads use hash suffix — find by prefix
        candidates = list(UPLOADS.glob(f"{iso}_*.json"))
        if not candidates:
            raise SystemExit(f"Missing JSON for {iso}")
        json_src = candidates[0]
        pdf_candidates = list(UPLOADS.glob(f"bao-sang-{iso}_*.pdf"))
        if not pdf_candidates:
            raise SystemExit(f"Missing PDF for {iso}")
        pdf_src = pdf_candidates[0]

        dest_dir = ISSUES / iso
        dest_dir.mkdir(parents=True, exist_ok=True)
        data = normalize(json.loads(json_src.read_text(encoding="utf-8")))
        (dest_dir / "content.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        shutil.copy2(pdf_src, dest_dir / "paper.pdf")
        dates.append(iso)

    dates.sort(reverse=True)
    index = {
        "masthead": MASTHEAD,
        "latest": dates[0],
        "issues": [{"date": d, "path": f"{d}/content.json"} for d in sorted(dates)],
    }
    (ISSUES / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Imported {len(dates)} issues; latest={dates[0]}")


if __name__ == "__main__":
    main()
