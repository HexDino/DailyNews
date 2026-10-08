#!/usr/bin/env python3
"""Rewrite local css/js references in HTML for GitHub Pages deploy (CI only)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FULL_SHA = sys.argv[1] if len(sys.argv) > 1 else "dev"
SHORT = FULL_SHA.replace('"', "")[:10]

CSS_LINK = re.compile(
    r'(<link\b[^>]*\bhref="css/reader\.css)(?:\?[^"]*)?(")',
    re.I,
)
JS_SCRIPT = re.compile(
    r'(<script\b[^>]*\bsrc="js/reader\.js)(?:\?[^"]*)?(")',
    re.I,
)
HTML_OPEN = re.compile(r"(<html\b)([^>]*)(>)", re.I)
ASSET_VER = re.compile(r'\sdata-asset-version="[^"]*"')


def bust_html(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    text = CSS_LINK.sub(rf'\1?v={SHORT}\2', text)
    text = JS_SCRIPT.sub(rf'\1?v={SHORT}\2', text)

    def html_attrs(m: re.Match[str]) -> str:
        attrs = ASSET_VER.sub("", m.group(2))
        return f'{m.group(1)}{attrs} data-asset-version="{SHORT}"{m.group(3)}'

    text = HTML_OPEN.sub(html_attrs, text, count=1)
    path.write_text(text, encoding="utf-8")


def main() -> int:
    html_files = sorted(ROOT.glob("*.html"))
    for path in html_files:
        bust_html(path)
    print(f"Cache-bust applied (v={SHORT}) to: {', '.join(p.name for p in html_files)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
