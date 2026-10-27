# Slow Reads article schema

Long-form life essays live under `slow-reads/`, independent of daily issues. The list page is `slow-reads/index.html`; a single article is `slow-reads/article.html?id=<slug>`.

For the fetch → translate → publish workflow (and the bot prompts), see [SLOW_READS_PIPELINE.md](SLOW_READS_PIPELINE.md).

## Add an article (bot / human)

1. Create `slow-reads/articles/<id>.json` (filename stem **must** equal the `id` field).
2. Run:
   ```bash
   python3 scripts/add_slow_read.py
   ```
   This rebuilds `slow-reads/articles/index.json` (list metadata only — full text stays in each article file).
3. Commit `slow-reads/articles/<id>.json` and `slow-reads/articles/index.json`, then push `main`.

Do **not** edit `index.json` by hand; the script is the source of truth for the list.

## Article file (`slow-reads/articles/<id>.json`)

| Field | Required | Description |
| --- | --- | --- |
| `id` | yes | URL slug (`[a-z0-9-]+`). Must match the filename stem. |
| `title` | yes | Vietnamese display title. |
| `title_original` | no | Original-language title when translated (shown under the Vietnamese title). |
| `author` | yes | Author name. |
| `source` | yes | Publication / site name. |
| `source_url` | no | Link to the original. |
| `lang` | yes | Original language code: `vi` for Vietnamese originals, `en` (or other) when the Vietnamese text is a translation. Non-`vi` shows a **Bản dịch tiếng Việt** note on the article page. |
| `topics` | yes | Array of topic labels (see below). |
| `summary` | yes | Short card description (1–2 sentences). |
| `added` | yes | Date the piece entered the library (`YYYY-MM-DD`). |
| `reading_minutes` | yes | Estimated minutes (integer ≥ 1). |
| `body` | yes | Non-empty array of content blocks (full readable text). |

### `body[]` blocks

| `type` | Fields | Renders as |
| --- | --- | --- |
| `p` | `text` | Paragraph |
| `h2` | `text` | Section heading |
| `h3` | `text` | Subheading |
| `quote` | `text`, optional `cite` | Blockquote (optional attribution) |

Example:

```json
{
  "id": "doi-ngan-lam-dung-phi-vao-chuyen-nham-nhi",
  "title": "Đời ngắn lắm, đừng phí vào chuyện nhảm nhí",
  "title_original": "Life is Short",
  "author": "Paul Graham",
  "source": "paulgraham.com",
  "source_url": "https://paulgraham.com/vb.html",
  "lang": "en",
  "topics": ["Con người", "Tư duy & khoa học"],
  "summary": "Ai cũng biết đời người ngắn…",
  "added": "2026-10-26",
  "reading_minutes": 8,
  "body": [
    { "type": "p", "text": "Bài “Life is Short” … bản lược dịch." },
    { "type": "p", "text": "Ai cũng biết đời người ngắn…" },
    { "type": "quote", "text": "…", "cite": "Paul Graham" },
    { "type": "h2", "text": "Tuỳ chọn tiêu đề phụ" }
  ]
}
```

## Topics

Default chip set on the list page (always offered for filtering):

- Con người
- Tình yêu
- Sự nghiệp
- Đối nhân xử thế
- Tiền bạc
- Tâm lý
- Tư duy & khoa học
- Stoicism

Any other string in an article’s `topics` is included in the filter chips as well (script appends extras after the canonical list). Prefer the defaults when they fit.

## Index file (`slow-reads/articles/index.json`)

Produced only by `scripts/add_slow_read.py`:

```json
{
  "version": 1,
  "topics": ["Con người", "…"],
  "articles": [
    {
      "id": "…",
      "title": "…",
      "title_original": "…",
      "author": "…",
      "source": "…",
      "source_url": "…",
      "lang": "en",
      "topics": ["…"],
      "summary": "…",
      "added": "YYYY-MM-DD",
      "reading_minutes": 5
    }
  ]
}
```

Articles are sorted newest `added` first (then `id`). Full `body` is **not** copied into the index.

## Relation to daily issues

The Slow Reads library under `slow-reads/` is separate from daily issue `content.json` files. Legacy URLs under `/doc-cham/` redirect to `/slow-reads/`.
