# PDF build (Daily News)

WeasyPrint + Jinja2, giống pipeline e-ink gốc nhưng masthead cố định **Daily News**.

## Font

Đặt các file TTF vào `fonts/`:

- `SourceSerifPro-Regular.ttf`
- `SourceSerifPro-It.ttf`
- `SourceSerifPro-Semibold.ttf`
- `SourceSerifPro-Bold.ttf`

Nếu thiếu font, WeasyPrint dùng fallback serif; với tiếng Việt nên có đủ bộ Source Serif Pro.

## Cài đặt

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Trên Linux cần dependency hệ thống của WeasyPrint (pango, cairo) — xem [WeasyPrint docs](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html).

## Build

```bash
.venv/bin/python build.py ../issues/2026-10-05/content.json -o ../issues/2026-10-05/paper.pdf --png
```
