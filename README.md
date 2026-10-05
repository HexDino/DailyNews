# Daily News

Báo sáng tiếng Việt dạng trang tĩnh: đọc trên trình duyệt như lật báo giấy, lọc theo mục, xem/tải PDF in, lưu số yêu thích (localStorage), và mở lại các số trong kho lưu trữ.

## Đọc trực tuyến (GitHub Pages)

Sau khi bật Pages (workflow `Deploy GitHub Pages` trên nhánh `main`):

**https://hexdino.github.io/DailyNews/**

- Trang chủ: số mới nhất (hoặc `?date=YYYY-MM-DD` để mở một ngày cụ thể).
- Lọc mục: tham số `?tag=ai|github|football|politics|culture|lifestyle` (hoặc `#tag=…`).
- Kho số cũ: [`archive.html`](archive.html).

## Thêm một số báo mới

1. Tạo thư mục `issues/YYYY-MM-DD/`.
2. Đặt **`content.json`** (cùng schema bên dưới) và **`paper.pdf`** (bản in).
3. Cập nhật chỉ mục:
   ```bash
   python3 scripts/regenerate_index.py
   ```
4. Commit và push lên `main` — workflow Pages sẽ deploy lại.

Tuỳ chọn: sinh PDF từ JSON bằng WeasyPrint trong [`pdf-build/`](pdf-build/):

```bash
cd pdf-build
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# Thêm font Source Serif Pro vào pdf-build/fonts/ (xem pdf-build/README.md)
.venv/bin/python build.py ../issues/2026-10-05/content.json -o ../issues/2026-10-05/paper.pdf
```

## Schema `content.json`

```json
{
  "date": "2026-10-05",
  "masthead": "Daily News",
  "tagline": "dòng phụ dưới ngày (tuỳ chọn)",
  "cover": true,
  "highlights": ["5 tiêu đề Điểm nhanh"],
  "sections": [
    {
      "title": "Trí tuệ nhân tạo",
      "tags": ["ai"],
      "intro": "tuỳ chọn",
      "items": [
        {
          "headline": "Tiêu đề",
          "meta": "dòng phụ",
          "body": "đoạn văn hoặc mảng đoạn",
          "tags": ["ai"],
          "sources": [{ "name": "Reuters", "url": "https://..." }]
        }
      ]
    }
  ],
  "footer_note": "tuỳ chọn"
}
```

Mục trên web map tới tag: AI (`ai`), Kho GitHub (`github`), Bóng đá (`football`), Chính trị (`politics`), Văn hoá (`culture`), Đời sống (`lifestyle`). Trường `tags` trên section/item là tuỳ chọn cho các số tương lai.

## Bot / tự động hoá xuất bản hằng ngày

1. Bot tạo hoặc cập nhật `issues/<ngày>/content.json` (masthead luôn **Daily News**).
2. Chạy `pdf-build/build.py` để ghi `issues/<ngày>/paper.pdf` (hoặc upload PDF có sẵn).
3. Chạy `python3 scripts/regenerate_index.py`.
4. `git add issues/` && commit && push `main`.

Không cần build frontend — site là HTML/CSS/JS tĩnh.

## Cấu trúc repo

```
index.html, archive.html
css/reader.css
js/reader.js
issues/index.json
issues/YYYY-MM-DD/content.json
issues/YYYY-MM-DD/paper.pdf
pdf-build/          # pipeline PDF (WeasyPrint)
scripts/            # import & regenerate index
.github/workflows/pages.yml
```

## Phát triển cục bộ

```bash
python3 -m http.server 8080
# Mở http://127.0.0.1:8080/
```

Trên GitHub Pages, script tự nhận base path `/DailyNews/`.
