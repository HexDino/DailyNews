# Slow Reads article schema

Long-form life essays live under `slow-reads/`, independent of daily issues. The list page is `slow-reads/index.html`; a single article is `slow-reads/article.html?id=<slug>`.

For the fetch → translate → publish workflow (and the bot prompts), see [SLOW_READS_PIPELINE.md](SLOW_READS_PIPELINE.md).

## Add an article (bot / human)

1. Fetch the source (cache only, never committed):
   ```bash
   python3 scripts/fetch_source.py "<url>" --id <id>
   ```
2. Create `slow-reads/articles/<id>.json` (filename stem **must** equal the `id` field) following the allowlist mode: `full` = translate everything, `excerpt` = 2–3 paragraphs + source link.
3. Attach coverage measurements:
   ```bash
   python3 scripts/attach_source_stats.py --coverage <full|excerpt> <id>
   ```
   Add `--coverage condensed` only for an intentionally abridged legacy post.
4. Run:
   ```bash
   python3 scripts/rights_gate.py slow-reads/articles/<id>.json
   python3 scripts/add_slow_read.py
   python3 scripts/validate_slow_read.py --strict
   ```
   `rights_gate.py` checks the allowlist: `coverage: full` needs a `basis` that permits derivative works (`public-domain`, `CC-BY*` without ND/NC, or `user-confirmed-permission` with `evidence`). `add_slow_read.py` rebuilds `slow-reads/articles/index.json` (list metadata only — full text stays in each article file).
5. Commit `slow-reads/articles/<id>.json` and `slow-reads/articles/index.json`, then push `main`.

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
| `source_published` | required from 2026-11-01 | Publication date of the original (`YYYY-MM-DD`). The licence gate rejects anything before **2000-01-01**, and rejects a new article that omits the field. Legacy articles are grandfathered. |
| `lang` | yes | Original language code: `vi` for Vietnamese originals, `en` (or other) when the Vietnamese text is a translation. Non-`vi` shows a **Bản dịch tiếng Việt** note on the article page. |
| `topics` | yes | Array of topic labels (see below). |
| `summary` | yes | Short card description (1–2 sentences). |
| `added` | yes | Date the piece entered the library (`YYYY-MM-DD`). |
| `reading_minutes` | yes | Estimated minutes (integer ≥ 1). |
| `body` | yes | Non-empty array of content blocks (full readable text). |
| `source_stats` | yes | Source measurements for coverage checks. See below. |

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

## Source stats (`source_stats`)

Produced by `scripts/attach_source_stats.py` from `.cache/slow-reads/<id>/source.txt`. It stores numbers only — never the source text.

| Field | Required | Description |
| --- | --- | --- |
| `url` | yes | Source URL from `meta.json`. |
| `coverage` | yes | `full` (default), `excerpt` for a 2–3 paragraph preview, `summary` for a 250–900 word rewrite of the ideas, or `condensed` for an intentionally abridged legacy post. |
| `word_count` | yes | Whitespace-separated words in the normalized source. |
| `char_count` | yes | Source characters excluding whitespace. |
| `paragraph_count` | yes | Non-empty source blocks. |
| `sentence_count` | yes | Sentences (≥3 words) in the normalized source. |
| `heading_count` | yes | Section headings (`##`–`######`); the `#` title is excluded. |
| `sha256` | yes | SHA-256 of the normalized source text; matches the cached source. |

Example:

```json
"source_stats": {
  "url": "https://paulgraham.com/vb.html",
  "coverage": "full",
  "word_count": 1691,
  "char_count": 7524,
  "paragraph_count": 27,
  "sentence_count": 113,
  "heading_count": 0,
  "sha256": "cdd2f7e1…"
}
```

Validation rules:

- Missing `source_stats` is a warning, fatal in CI (`--strict`).
- `coverage: "full"`: fatal when the translation is under 45% of source characters or 50% of source sentences.
- `coverage: "excerpt"`: fatal when the body exceeds 8 blocks, 1800 characters, or 50% of source length; must keep `source_url`.
- Block and heading counts are informational (paragraph merging and sentence splitting vary by language).
- `coverage: "condensed"`: all coverage metrics are informational; schema checks still apply.
- `coverage: "summary"`: fatal when the body is outside **250–900 words**, when it exceeds **30%** of source characters, or when `source_url` is missing. A summary states ideas and facts in the writer's own words with attribution — it must not become an abridged translation, which needs the same licence as a full one. Short quotations are fine; keep them to one or two sentences. For a source of 3,000+ words, aim for 700–900 words: length comes from covering more of the argument, not from following the original's sentences.

## Licence gate (`scripts/rights_gate.py`)

Schema validity is not permission to publish. A translation is a derivative work, so `coverage: "full"` and `"condensed"` additionally require an allowlist entry that permits derivatives:

| `basis` | full / condensed |
| --- | --- |
| `public-domain` | allowed |
| `CC-BY`, `CC-BY-SA`, `CC-BY-4.0`… | allowed (attribution; SA also share-alike) |
| `CC-BY-ND`, `CC-BY-NC`, `CC-BY-NC-ND` | **blocked** — ND/NC forbid the derivative |
| `user-confirmed-permission` + `evidence` | allowed |
| `user-confirmed-permission`, no `evidence` | warning only, CI passes |
| `excerpt-only` | **blocked** |

`coverage: "excerpt"` needs any allowlist entry and must keep `source_url`. `coverage: "summary"` is allowed for **any** allowlisted source — it carries ideas, not expression — but the word cap (250–900) and the 30% length cap are enforced, so it cannot drift back into an abridged translation. The gate also rejects an article whose `source_stats.url` host differs from `source_url`, and any entry past its `expires_at`. CI runs it before deploy, so a full translation of a protected source cannot reach the live site.

`python3 scripts/rights_gate.py --mode <id>` prints the resolved `full` / `excerpt` / `skip` for an article id — the runner uses it to pick the right prompt.

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
