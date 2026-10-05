#!/usr/bin/env python3
"""Build Daily News print PDF from a JSON content file (WeasyPrint).

Usage:
  .venv/bin/python build.py ../issues/2026-10-05/content.json
  .venv/bin/python build.py content.json -o ../issues/2026-10-05/paper.pdf --png
"""
import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

HERE = Path(__file__).resolve().parent
THU = ["Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật"]
MASTHEAD = "Daily News"


def vn_date(d: date) -> str:
    return f"{THU[d.weekday()]}, {d.day} tháng {d.month}, {d.year}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("content")
    ap.add_argument("-o", "--output")
    ap.add_argument("--page-size", default="157mm 210mm")
    ap.add_argument("--font-size", default="12.5pt")
    ap.add_argument(
        "--png",
        action="store_true",
        help="render page 1 to PNG (1404 px wide) via pdftoppm",
    )
    ap.add_argument("--html", action="store_true", help="also write the intermediate HTML")
    a = ap.parse_args()

    data = json.loads(Path(a.content).read_text(encoding="utf-8"))
    d = date.fromisoformat(data["date"])
    ctx = {
        "masthead": MASTHEAD,
        "tagline": data.get("tagline", ""),
        "date_vn": data.get("date_vn") or vn_date(d),
        "date_short": f"{d.day}/{d.month}/{d.year}",
        "highlights": data["highlights"],
        "sections": data["sections"],
        "footer_note": data.get("footer_note", ""),
        "cover": data.get("cover", True),
        "page_size": a.page_size,
        "font_size": a.font_size,
    }
    env = Environment(
        loader=FileSystemLoader(HERE),
        autoescape=select_autoescape(["html"]),
    )
    html = env.get_template("template.html").render(**ctx)
    out = Path(a.output) if a.output else HERE / f"daily-news-{d.isoformat()}.pdf"
    if a.html:
        out.with_suffix(".html").write_text(html, encoding="utf-8")
    doc = HTML(string=html, base_url=str(HERE)).render()
    doc.write_pdf(out)
    print(f"PDF: {out}  pages: {len(doc.pages)}")
    if a.png:
        prefix = out.with_name(out.stem + "-p1")
        subprocess.run(
            [
                "pdftoppm",
                "-png",
                "-gray",
                "-f",
                "1",
                "-l",
                "1",
                "-scale-to-x",
                "1404",
                "-scale-to-y",
                "-1",
                "-singlefile",
                str(out),
                str(prefix),
            ],
            check=True,
        )
        print(f"PNG: {prefix}.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
