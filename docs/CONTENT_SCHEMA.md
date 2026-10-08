# Daily News `content.json` schema

Each issue lives in `issues/<issue-id>/content.json`. The issue id is usually `YYYY-MM-DD` (morning) or `YYYY-MM-DD-chieu` (evening). Run `python3 scripts/regenerate_index.py` after adding or editing an issue so `issues/index.json` and `issues/search-index.json` stay in sync.

## Top-level fields

| Field | Required | Description |
| --- | --- | --- |
| `date` | yes | Calendar date (`YYYY-MM-DD`) for the issue. Evening editions still use the calendar date, not the `-chieu` suffix. |
| `masthead` | no | Display name (site uses `Daily News` in the reader). |
| `date_vn` | no | Vietnamese date line; generated on the site if omitted. |
| `tagline` | no | Subtitle under the date. |
| `edition` | no | `"chieu"` for evening editions. |
| `edition_label` | no | e.g. `Số buổi chiều`. |
| `cover` | no | PDF: show “Trong số này” TOC on page 1 (default true in PDF builder). |
| `topics` | no | List of topic names used in newer layouts. |
| `highlights` | yes | Array of strings for **Điểm nhanh**. |
| `followups` | no | Ongoing stories (**Theo dõi tin cũ**). See below. |
| `calendar` | no | Upcoming events (**Lịch sự kiện**). See below. |
| `sections` | yes | Array of section objects (articles). |
| `footer_note` | no | Italic footer on web and PDF. |

## Section object

Legacy morning issues use a flat section:

```json
{
  "title": "Trí tuệ nhân tạo",
  "intro": "Optional lead paragraph.",
  "tags": ["ai"],
  "items": [ ]
}
```

Newer issues group by **topic** and optional **subtitle** (subsection):

```json
{
  "topic": "Công nghệ",
  "subtitle": "AI",
  "title": "Công nghệ · AI",
  "tags": ["tech", "ai"],
  "intro": "Optional.",
  "items": [ ]
}
```

Evening-only section names (e.g. `Chính trị Việt Nam`, `Bên lề & Fact hôm nay`) use the same shape with `title` and optional `tags`.

## Article (`items[]`)

| Field | Required | Description |
| --- | --- | --- |
| `headline` | yes | Title. |
| `meta` | no | Byline / timing line. |
| `body` | no | String or array of paragraphs. |
| `tags` | no | Filter tags: `tech`, `ai`, `github`, `construction`, `football`, `politics`, `culture`, `lifestyle`. |
| `sources` | no | Array of `{ "name": "...", "url": "https://..." }` (`url` optional). |

## Follow-ups (`followups[]`)

| Field | Required | Description |
| --- | --- | --- |
| `title` | yes | Story headline. |
| `update` | yes | Vietnamese text describing what is new in this issue. |
| `status` | yes | `"đang diễn biến"` or `"đã kết thúc"`. |
| `first_issue` | yes | Issue id where the story first ran (linked on the site). |
| `sources` | no | Same shape as article sources. |

## Calendar (`calendar[]`)

| Field | Required | Description |
| --- | --- | --- |
| `date` | yes | `YYYY-MM-DD`. |
| `time` | no | Time string (e.g. `14:00` or `trong ngày`). |
| `timezone` | no | Label shown with time; default **giờ VN** on the site if omitted. |
| `title` | yes | Event name. |
| `topic` | yes | One of the standard topics (e.g. `Công nghệ`, `Xây dựng`, `Chính trị`). |
| `note` | no | Short extra context. |
| `sources` | no | Same shape as article sources. |

See `issues/2026-10-08/content.json` for a full example with `followups` and `calendar`. Issues without those fields render unchanged.
