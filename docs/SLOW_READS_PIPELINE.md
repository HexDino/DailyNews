# Slow Reads pipeline — nguồn, dịch, xuất bản

Pipeline tách việc lấy nguồn, dịch và đăng bài thành ba chặng độc lập. Mục tiêu: bước tìm nguồn **không phải tái tạo nguyên văn** nội dung có bản quyền, nên không bị giới hạn "chỉ trích dẫn ngắn"; bản dịch do Claude thực hiện từ file nguồn; bước publish chỉ chạy lệnh kiểm tra rồi commit.

```
discovery (Grok/người)   scripts/fetch_source.py        Claude (translate)         run-batch.ps1 (publish)
URL + metadata    ──►    source.txt + meta.json   ──►   articles/<id>.json   ──►   validate + gate + commit
(không body)             (.cache, không commit)         + source_stats (số đo)     (không đọc body)
```

Grok Bot là app chat trên desktop — nó **không** chạy được script, không có scheduled task, không đọc repo. Nó chỉ soạn prompt và script; mọi bước thực thi là chạy tay hoặc do `run-batch.ps1` làm.

## Phân chia nhiệm vụ

| Việc | Ai làm |
| --- | --- |
| Soạn số báo hằng ngày (`issues/<id>/content.json`) | Grok |
| Tìm link + metadata cho Slow Reads (không đọc body) | Grok |
| Dịch Slow Reads, validate, gate, commit, push | WorkBuddy |
| Build PDF, rebuild index, deploy | WorkBuddy |

Prompt cấu hình vai trò Grok: [`GROK_ROLE.md`](GROK_ROLE.md). Prompt này thay cho hai khối "Grok — discovery" và "Grok — publish" bên dưới, vốn giả định Grok chạy được lệnh.

**Automation đang chạy**: hai lịch, cả hai đều tự commit và push.

| Lịch | Việc | Tần suất |
| --- | --- | --- |
| 07:00 | Dịch **toàn văn** một tác phẩm public domain (≤25.000 từ, nới ≤50.000 nếu bậc đầu rỗng) | hằng ngày |
| 19:00 | Viết **tóm tắt** 250–600 từ cho một bài đương đại lấy từ queue hoặc RSS | thứ Hai, Tư, Sáu |

Cả hai đều dừng nếu `validate --strict` hoặc `rights_gate` báo lỗi. Đổi tần suất trong phần Automations của WorkBuddy.

Runway hiện tại: **16 tác phẩm ≤25.000 từ** và **40 tác phẩm ≤50.000 từ** — khoảng 40 ngày ở nhịp ngày. Muốn chạy dài hơn thì bổ sung catalogue; tra ID bằng `pg_catalog.csv` như trên.

`source_stats` là các con số đo nguồn (số từ/ký tự/đoạn/câu/heading + sha256), do `scripts/attach_source_stats.py` sinh ra. Nó cho phép CI kiểm độ phủ bản dịch mà **không cần** đưa nội dung nguồn lên repo.

## Hợp đồng file

| File | Ai tạo | Có commit? | Nội dung |
| --- | --- | --- | --- |
| `.cache/slow-reads/<cache-id>/source.txt` | `scripts/fetch_source.py` | Không (gitignored) | Toàn văn nguồn đã trích, dạng Markdown |
| `.cache/slow-reads/<cache-id>/meta.json` | `scripts/fetch_source.py` | Không | `url`, `title`, `author`, `sitename`, `language`, `word_count`… |
| `slow-reads/articles/<id>.json` | Claude | Có | Bản dịch + `source_stats` (số đo nguồn, không chứa nội dung) |
| `slow-reads/articles/index.json` | `scripts/add_slow_read.py` | Có | Chỉ mục thư viện; không sửa tay |

`cache-id` không bắt buộc trùng `id` của bài: validator tự dò nguồn theo `source_url` trong `meta.json`. Vẫn nên dùng cùng một slug cho dễ tra cứu.

Không sửa tay `source_stats`; chạy lại `attach_source_stats.py` sau khi đổi bản dịch hoặc nguồn.

## Nguồn & discovery

Registry: `slow-reads/sources.json` (commit). Mỗi nguồn có `id`, `name`, `domain`, `topics`, `lang`, `rss`, `fetch` (`rss+static` / `static` / `js`), `quality` (0–100), `max_per_week`, `notes`. Top-level có `rights_policy` và `title_blocklist` để lọc reading list/roundup/podcast.

Queue: `slow-reads/queue.json` (commit) là ledger discovery/publish:

```json
{
  "version": 1,
  "rights_policy": "user-accepted",
  "items": [
    {
      "url": "https://...",
      "title": "...",
      "author": "...",
      "source": "...",
      "source_id": "aeon",
      "lang": "en",
      "topics_guess": ["Con người"],
      "quality_score": 92,
      "quality_reason": "một câu",
      "est_words": 0,
      "fetch": "rss+static",
      "rights_note": "user-accepted",
      "status": "candidate",
      "note": "",
      "added_at": "YYYY-MM-DD"
    }
  ]
}
```

Khi publish, thêm `id`, `published_at`, `published_url`, `published_sha`.

Status thực dùng: `candidate` → `published`. Các trạng thái `rights_approved` / `translating` / `ready` / `blocked` / `skipped` / `rejected` có trong thiết kế nhưng chưa dùng — thêm vào đây khi có script ghi queue.

`rights_note` **không phải giấy phép**. Nó chỉ ghi rằng người dùng tự chấp nhận rủi ro. Quyền publish do `rights_allowlist.json` quyết định và do `scripts/rights_gate.py` cưỡng chế.

Allowlist: `slow-reads/rights_allowlist.json` (commit). `default: "skip"`; Grok chỉ xử lý URL khớp `match` (`domain:`, `url:` hoặc `path:`). Không khớp thì bỏ qua im lặng, ghi `skipped`, không hỏi người dùng.

```json
{
  "version": 2,
  "updated_at": "YYYY-MM-DD",
  "default": "skip",
  "allowed_domains": ["aeon.co", "..."],
  "entries": [
    {
      "match": "domain:aeon.co",
      "domain": "aeon.co",
      "scope": "domain",
      "mode": "excerpt",
      "basis": "excerpt-only",
      "license": null,
      "approved_by": "user",
      "approved_at": "YYYY-MM-DD",
      "expires_at": null,
      "note": "Excerpt and link only; no full translation."
    }
  ]
}
```

- `mode: "full"`: chỉ dùng cho `public-domain`, `user-confirmed-permission` **có kèm `evidence`**, hoặc `CC-...` cho phép tác phẩm phái sinh.
- `mode: "excerpt"`: chỉ đăng 2–3 đoạn + link; **không** dịch toàn bộ.
- `basis`: `public-domain`, `user-confirmed-permission`, `CC-...`, hoặc `excerpt-only`. Không tự gán license.
- `evidence` (tuỳ chọn): đường dẫn hoặc URL tới văn bản cho phép bằng văn bản. Không có `evidence` thì `user-confirmed-permission` chỉ là lời khai — `rights_gate.py` sẽ cảnh báo to.
- Hiện allowlist phủ 32 domain: 4 domain full (Paul Graham, Tia Sáng, Gutenberg, Standard Ebooks) và 28 domain excerpt. Paul Graham/Tia Sáng đang ở dạng "người dùng khai có phép" **không kèm văn bản** — gate cảnh báo từng bài mỗi lần chạy. Nếu không có văn bản thật, đổi sang `mode: "excerpt"` và chạy `make_excerpt.py`.
- Nguồn ngoài allowlist bị chặn ở bước publish, không hỏi.

## Cổng giấy phép (`scripts/rights_gate.py`)

Bản dịch là **tác phẩm phái sinh**. Đăng công khai bản dịch toàn văn cần giấy phép cho phép phái sinh, và không có câu prompt nào thay đổi được điều đó — nên quy tắc này được cưỡng chế bằng code, không bằng lời dặn.

```bash
python3 scripts/rights_gate.py                       # kiểm mọi bài
python3 scripts/rights_gate.py slow-reads/articles/x.json
python3 scripts/rights_gate.py --mode <id>           # in ra full|excerpt|skip
```

| `basis` | `coverage: full` / `condensed` |
| --- | --- |
| `public-domain` | cho phép |
| `CC-BY`, `CC-BY-SA`, `CC-BY-4.0`… | cho phép (ghi công; SA kèm share-alike) |
| `CC-BY-ND`, `CC-BY-NC`, `CC-BY-NC-ND` | **chặn** — ND/NC cấm bản phái sinh |
| `user-confirmed-permission` + `evidence` | cho phép |
| `user-confirmed-permission` không `evidence` | cảnh báo, không chặn CI |
| `excerpt-only` | **chặn** |

`coverage: "summary"` là ngoại lệ có kiểm soát: cho phép với **mọi** nguồn trong allowlist, kể cả `excerpt-only`, vì nó truyền đạt ý và sự kiện bằng lời người viết chứ không lấy cách diễn đạt của tác giả. Hai trần được cưỡng chế cứng: **250–600 từ** và **≤40% độ dài nguồn**. Vượt trần là thành bản dịch rút gọn, và gate chặn — đó chính là điểm khác biệt giữa "tóm tắt" và "dịch bớt".

Cách làm: `python3 scripts/attach_source_stats.py --coverage summary <id>`, rồi validate và gate như thường. Body nên kết bằng `*Bản tóm tắt — đọc toàn bài tại <nguồn>.*` để người đọc biết đây không phải bản dịch.

`coverage: "excerpt"` chỉ cần một entry bất kỳ và phải giữ `source_url`. CI chạy gate trước bước deploy, nên bản dịch toàn văn của nguồn không có phép không lên được `hexdino.github.io`.

`--mode <id>` tự dò URL theo thứ tự: file bài viết → `.cache/slow-reads/<id>/meta.json` → `queue.json` (khớp `id`). Runner dùng lệnh này để chọn chế độ, nên prompt luôn khớp giấy phép.

Chuyển bài đang full sang excerpt theo allowlist:

```bash
python3 scripts/make_excerpt.py --all-excerpt --dry-run
python3 scripts/make_excerpt.py --all-excerpt
```

Script giữ 2–3 đoạn đầu (tối đa ~1400 ký tự), thêm dòng “Trích đoạn — đọc toàn bài tại …”, đặt `source_stats.coverage = "excerpt"` và backup bản full vào `.cache/full-backup/` (local). Validator fail nếu excerpt vượt 8 block / 1800 ký tự / 50% độ dài nguồn.

Discovery từ RSS (không tải body, chỉ title/link/ngày/excerpt ≤280 ký tự):

```bash
python3 scripts/discover_rss.py --limit 20 --days 60 --per-source 3 \
  --out .cache/candidates.json --pretty
```

- `--sources aeon,psyche`: chỉ chạy một số nguồn.
- `--min-quality 75`: bỏ nguồn dưới ngưỡng (mặc định 75; dùng `0` để lấy tất cả).
- `--no-diversify`: xếp theo quality/ngày thay vì xen kẽ nguồn.
- `--no-blocklist`: giữ cả tiêu đề khớp `title_blocklist`.
- `--allow-undated`, `--no-cache`, `--cache-ttl`.

Output có `source_id, source, url, title, author, published, summary, topics, lang, quality, fetch, feed_mode`. Feed được cache trong `.cache/rss/` (gitignored); nếu feed lỗi, script dùng cache cũ và cảnh báo. Nguồn `rss: null` (Tia Sáng, Vietcetera, Works in Progress…) phải thêm thủ công vào queue sau khi người dùng duyệt URL.

## Public domain — nguồn duy nhất dịch toàn văn được

Báo đương đại gần như đều `all rights reserved`. Public domain thì không: dịch, đăng, bán đều được. Đây là nơi thư viện nên dày lên.

**Catalogue**: `slow-reads/public-domain.json` — 73 tác phẩm, trải 8 chủ đề. Mỗi entry có `gutenberg_id` **đã đối chiếu**, `topics`, `est_words`, và `note` giải thích vì sao hợp chủ đề. Không dùng RSS của Gutenberg làm nguồn chính: feed đó chỉ liệt kê sách tải lên hôm nay, không liên quan gì tới chủ đề.

Nguồn tra ID: **`https://www.gutenberg.org/cache/epub/feeds/pg_catalog.csv`** (~21 MB, 90k dòng, có cột Authors/Subjects/Bookshelves). Tải một lần rồi grep local — nhanh và không bị rate limit. Gutendex (`gutendex.com`) cũng dùng được nhưng hay trả 503; chỉ nên dùng khi cần metadata bổ sung.

```bash
# Xem ứng viên, ngắn trước, xen kẽ chủ đề
python3 scripts/discover_pd.py --table
python3 scripts/discover_pd.py --topics Stoicism --max-words 40000
python3 scripts/discover_pd.py --limit 5 --out .cache/pd-candidates.json --pretty
```

`--max-words` mặc định 80.000 để không ai vô tình bắt đầu dịch Montaigne (500k từ) trong một lượt. `0` = không giới hạn. Output cùng schema với `discover_rss.py`, thêm `gutenberg_id`, `est_words`, `title_original`, `suggested_id`.

**Tải nguồn**: `fetch_source.py` tự cắt header/footer Project Gutenberg (`*** START OF… ***`, khối `**Title**: / **Credits**:`) và cắt luôn phần licence. Metadata Gutenberg hay sai tên tác giả, nên truyền đè:

```bash
python3 scripts/fetch_source.py "https://www.gutenberg.org/cache/epub/2680/pg2680-images.html" \
  --id suy-tuong-marcus-aurelius --title "Meditations" --author "Marcus Aurelius"
```

**Chất lượng bản in khác nhau giữa các edition.** Ví dụ #45109 (Enchiridion) là bản in 1948 kèm trang bìa và catalogue nhà xuất bản ở cuối. Prompt dịch đã dặn bỏ front matter/back matter, nhưng vẫn nên mở `source.txt` xem 200 ký tự đầu và cuối trước khi dịch — rẻ hơn nhiều so với sửa một bài đã đăng.

**Môi trường**: `fetch_source.py` cần `trafilatura`.

```bash
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r scripts/requirements.txt   # Windows
# hoặc .venv/bin/python -m pip install -r scripts/requirements.txt    # macOS/Linux
```

`standardebooks.org` cũng là public domain và bản in sạch hơn Gutenberg; feed `new-releases` đã bật trong `sources.json`, feed đầy đủ cần auth.

## Chạy tay

```bash
pip install -r scripts/requirements.txt      # Windows: python -m pip ...
python3 scripts/fetch_source.py "https://example.com/essay" --id ten-bai   # Windows: python
python3 scripts/rights_gate.py --mode ten-bai          # full | excerpt | skip
# Claude ghi slow-reads/articles/ten-bai.json theo đúng mode vừa in ra
python3 scripts/attach_source_stats.py ten-bai
python3 scripts/validate_slow_read.py slow-reads/articles/ten-bai.json
python3 scripts/rights_gate.py slow-reads/articles/ten-bai.json
python3 scripts/add_slow_read.py
python3 scripts/validate_slow_read.py --strict
```

- `--html FILE`: trích từ HTML đã lưu (khi trang chặn tải trực tiếp hoặc cần lưu bằng trình duyệt).
- `--favor-recall`: giữ nhiều chữ hơn, đổi lại có thể lẫn boilerplate.
- `--force`: ghi đè cache nguồn đã có.
- `--no-cache`: bỏ qua đối chiếu cache, dùng `source_stats` nhúng (giống CI).
- `--strict`: warning thành lỗi; CI dùng cờ này.
- `attach_source_stats.py --coverage condensed <id>`: chỉ dùng cho bài lược dịch cũ.
- `attach_source_stats.py --coverage excerpt <id>`: cho bài trích đoạn.
- `make_excerpt.py --all-excerpt`: chuyển các bài thuộc domain `mode: "excerpt"` sang trích đoạn.
- `make_excerpt.py --all-excerpt --from-backup`: cắt lại excerpt đã có từ `.cache/full-backup/` (không cần dịch lại). Bỏ đoạn bio/subscribe ở đầu và luôn nhắm 2–3 đoạn, tối đa 1800 ký tự.

## Chính sách độ phủ

- `full` (mặc định cho bài mới): CI fail nếu bản dịch dưới **45% ký tự** hoặc **50% số câu** của nguồn.
- `condensed`: cho bài lược dịch cũ/được chủ ý rút gọn; các chỉ số chỉ ghi chú, schema vẫn bắt buộc.
- `excerpt`: chỉ 2–3 đoạn + link; CI fail nếu vượt **8 block**, **1800 ký tự** hoặc **50% độ dài nguồn**.
- `summary`: 250–600 từ, ≤40% độ dài nguồn, bắt buộc `source_url`; CI fail nếu ra ngoài khoảng đó.
- Chỉ số blocks/headings chỉ ghi chú vì việc gộp đoạn và tách câu khác nhau theo ngôn ngữ.
- Khi có cache, validator còn đối chiếu `sha256`; trên CI chỉ dùng `source_stats` nhúng, không cần nguồn.
- Giới hạn: ngưỡng chỉ bắt thiếu thô (cả đoạn/cả mục). Không thay thế việc đọc đối chiếu thủ công.

## Chế độ public (B) — hiện tại

- `mode: "full"`: 9 bài. 4 domain: Gutenberg + Standard Ebooks (`public-domain`, không rủi ro) và Paul Graham + Tia Sáng (`user-confirmed-permission` **không có `evidence`** — gate cảnh báo 9/19 bài mỗi lần chạy).
- `mode: "excerpt"`: 10 bài còn lại, 2–3 đoạn + link nguồn.
- Bài từ nguồn excerpt **không được** dịch toàn bộ. Có văn bản cho phép thì thêm `evidence` vào allowlist, đổi `mode` sang `full`, khôi phục bản full từ `.cache/full-backup/` (local) hoặc dịch lại, rồi attach `--coverage full`.
- Chuyển file hiện tại sang excerpt **không xóa full text khỏi git history** của các commit cũ. Nếu cần xóa lịch sử, phải rewrite history hoặc tạo repo mới — việc này cần xác nhận riêng.

## Prompt cho bot

Các khối dưới đây là hợp đồng giữa các bước. Grok soạn prompt, người dùng chạy. Chỗ `<...>` là biến cần điền.

### 1. Grok — discovery

```text
VAI TRÒ: DISCOVERY cho thư viện Slow Reads của Daily News.
Bạn KHÔNG dịch, KHÔNG tóm tắt, KHÔNG trích nguyên văn nội dung bài.

Nguồn: chạy
python3 scripts/discover_rss.py --limit 30 --days 60 --out .cache/candidates.json
Chỉ chọn từ file này. Với nguồn rss:null trong slow-reads/sources.json, chỉ đề xuất
khi người dùng đã duyệt URL cụ thể. Không tự tìm web tự do; nguồn mới phải được
người dùng duyệt rồi thêm vào sources.json. Publish chỉ khi URL khớp
slow-reads/rights_allowlist.json; không khớp → skipped, không hỏi.

Đầu ra: CHỈ một JSON array, không markdown, không giải thích:
[
  {
    "source_id": "aeon",
    "url": "https://...",
    "title": "tiêu đề gốc",
    "author": "tên tác giả hoặc \"\"",
    "source": "tên trang",
    "lang": "en",
    "topics_guess": ["Tư duy & khoa học"],
    "quality_score": 0,
    "quality_reason": "một câu",
    "est_words": 0,
    "fetch": "rss+static|static|js"
  }
]

Quy tắc:
- Tối đa <N> bài/lượt; ít nhất 3 chủ đề khác nhau; tối đa 1 bài/nguồn, 1 bài/tác giả.
- Chỉ nhận quality_score >= 75; ưu tiên rss+static.
- Dedupe với slow-reads/articles/index.json và slow-reads/queue.json.
- topics_guess chọn từ: Con người, Tình yêu, Sự nghiệp, Đối nhân xử thế, Tiền bạc, Tâm lý, Tư duy & khoa học, Stoicism.
- Không bịa title/author; không rõ thì để "".
- Không trả về nội dung bài, không trích quá một câu.
```

### 2. Claude — translate

```text
VAI TRÒ: TRANSLATE cho thư viện Slow Reads của Daily News.
Schema bắt buộc: docs/SLOW_READS_SCHEMA.md.

Đầu vào:
- .cache/slow-reads/<cache-id>/source.txt  (toàn văn nguồn, Markdown)
- .cache/slow-reads/<cache-id>/meta.json   (url, title, author, sitename, language)
Nếu chưa có, chạy: python3 scripts/fetch_source.py "<url>" --id <cache-id>

Đọc slow-reads/rights_allowlist.json để biết mode của domain:
- mode "full": dịch TOÀN BỘ sang tiếng Việt.
- mode "excerpt": chỉ dịch 2-3 đoạn đầu (tối đa ~1400 ký tự), thêm block
  {"type":"p","text":"*Trích đoạn — đọc toàn bài tại <source>.*"};
  KHÔNG dịch phần còn lại.

Ghi đúng một file slow-reads/articles/<id>.json. Không in body ra chat; dùng công cụ ghi file.

Quy tắc nội dung:
- Với mode full: dịch đủ 100%, không lược đoạn, không thêm bình luận, không thay bằng tóm tắt.
- Với mode excerpt: giữ 2-3 đoạn đầu, không cắt giữa câu; tổng body ≤ ~1500 ký tự.
- Đoạn văn -> {"type":"p","text":"..."}
- Dòng "# " là tiêu đề bài (đã có ở title), KHÔNG tạo block.
- "##" -> {"type":"h2"}; "###" -> {"type":"h3"}
- ">" -> {"type":"quote"} kèm "cite" nếu có tên người nói
- Bỏ <sup>, số chú thích [1], **bold** và mọi markdown khác. Chỉ giữ *...* cho in nghiêng.
- title = tiêu đề tiếng Việt; title_original = meta.title.
- author = meta.author; source = meta.sitename; source_url = meta.url; lang = ngôn ngữ GỐC (bài gốc tiếng Việt thì "vi").
- id = slug tiếng Việt không dấu, chỉ [a-z0-9-], trùng tên file.
- summary = 1-2 câu tiếng Việt; reading_minutes = max(1, round(số từ / 180)).
- added = ngày hôm nay, dạng YYYY-MM-DD.

Gắn số đo nguồn và kiểm tra trước khi báo xong:
python3 scripts/attach_source_stats.py --coverage <full|excerpt> <id>
python3 scripts/validate_slow_read.py slow-reads/articles/<id>.json
python3 scripts/rights_gate.py slow-reads/articles/<id>.json
Sửa đến khi 0 error. Với full, warning dưới 45% ký tự hoặc 50% số câu nghĩa là đã bỏ sót — phải dịch bù.
Với excerpt, warning nếu vượt 8 block / 1800 ký tự / 50% độ dài nguồn — cắt bớt.
Không đặt condensed để né cảnh báo.
Nếu `rights_gate.py` chặn: dừng, báo lại mode và basis. Không đổi coverage, không sửa allowlist, không tìm cách lách — chuyển sang excerpt.
Báo cáo: đường dẫn file, mode, số block, số từ, coverage, kết quả validate + gate.
```

### 3. Grok — publish

```text
VAI TRÒ: PUBLISH cho thư viện Slow Reads của Daily News.
Bạn nhận một file slow-reads/articles/<id>.json đã dịch và validate xong.
Bạn KHÔNG đọc/in nội dung body, KHÔNG sửa bản dịch, KHÔNG dịch lại.

Đọc allowlist: mode của domain phải khớp source_stats.coverage
(full ↔ full, excerpt ↔ excerpt). Lệch → dừng, báo lỗi; không tự sửa.

Chạy tuần tự, dừng ngay nếu một lệnh thất bại:
1. python3 scripts/validate_slow_read.py slow-reads/articles/<id>.json
2. python3 scripts/rights_gate.py slow-reads/articles/<id>.json
3. python3 scripts/add_slow_read.py
4. python3 scripts/validate_slow_read.py --strict
5. git add slow-reads/articles/<id>.json slow-reads/articles/index.json
6. git commit -m "Add Slow Reads article <id>"
7. git push origin main

Nếu bước 1-4 báo lỗi: dừng, gửi nguyên văn lỗi cho người dịch. Không tự sửa nội dung, không tự thêm/sửa source_stats, không đặt coverage "condensed" để né cảnh báo, không sửa allowlist để qua gate.

Sau khi push, xác minh:
- git rev-parse HEAD và git rev-parse origin/main giống nhau.
- Workflow "Deploy GitHub Pages" chạy xanh (chờ 1-2 phút nếu cần).
- Mở https://hexdino.github.io/DailyNews/slow-reads/articles/index.json và xác nhận có "id": "<id>".

Báo cáo cuối: commit SHA, tổng số bài trong index, URL live của thư viện, lỗi còn tồn (nếu có).
```

### 4. Runner — `run-batch.ps1` (không phải Grok)

**Grok không gọi Claude.** Grok Bot là app chat trên desktop; nó không có quyền chạy script, không có scheduled task, không đọc repo. Việc orchestration do `C:\Users\hung1\dailynews-dich\run-batch.ps1` làm, chạy tay.

```powershell
cd C:\Users\hung1\dailynews-dich

# Xem trước prompt, không gọi Claude, không tốn tiền
.\run-batch.ps1 -Ids chuyen-co-con,tinh-yeu-khong-noi-de-ve -DryRun

# Chạy thật
.\run-batch.ps1 -Ids chuyen-co-con,lam-viec-cham-chi-the-nao

# Bài mới, cache chưa có nguồn
.\run-batch.ps1 -Ids bai-moi -Urls @{ 'bai-moi' = 'https://gutenberg.org/ebooks/1234' }
```

Runner làm theo thứ tự:

1. `rights_gate.py --mode <id>` → lấy `full` / `excerpt` / `skip` từ allowlist. `skip` thì dừng, không hỏi.
2. Cache nguồn thiếu → tự chạy `fetch_source.py`.
3. Sinh prompt theo đúng mode rồi chạy `claude -p --dangerously-skip-permissions`, tối đa `-MaxTries` lần, timeout `-TimeoutMin`.
4. `validate_slow_read.py` **không** `--strict` — chỉ lỗi thật mới tính là fail. Warning "missing from index.json" là bình thường ở bước này.
5. `rights_gate.py <file>` — gate không xanh thì không báo thành công.
6. Tất cả xanh → `add_slow_read.py` + `validate_slow_read.py --strict` một lần ở cuối.

Tham số: `-Repo` (mặc định `D:\Workspace\DailyNews`), `-MaxTries 2`, `-TimeoutMin 45`, `-MaxParallel 2` (số phiên `claude -p` song song), `-Claude` (đường dẫn CLI).

Ghi log vào `C:\Users\hung1\dailynews-dich\batch-<timestamp>-status.txt` và `claude-<id>-<try>.log`.

**Đừng** dùng lại `run-1028-b-runner.ps1` hay `runs/run1.ps1`: bản cũ validate `--strict` trước khi rebuild index nên bài nào cũng báo FAIL, hardcode "FULL translation" bất kể allowlist, và không có gate.

## Lưu ý

- **Không commit nội dung nguồn**: `.cache/` đã nằm trong `.gitignore`. Chỉ bản dịch lên repo.
- **Registry**: thêm nguồn mới vào `slow-reads/sources.json` sau khi người dùng duyệt; chạy `discover_rss.py` để lấy candidates. Nguồn `rss: null` thêm tay vào queue.
- **Rights policy**: registry/queue đang `user-accepted` — người dùng chấp nhận trách nhiệm; bot không được tự gán "public-domain"/"CC"/"written-permission" khi không có căn cứ.
- **Allowlist**: `slow-reads/rights_allowlist.json` quyết định nguồn nào được xử lý; mặc định `skip`. Không khớp thì bỏ qua im lặng, không hỏi.
- **Bản quyền**: dịch toàn văn và đăng công khai là tác phẩm phái sinh. Chỉ làm với nguồn cho phép hoặc chấp nhận rủi ro; ghi rõ tác giả/nguồn và link gốc.
- **CI** chạy `add_slow_read.py` + `validate_slow_read.py --strict` trước khi deploy. Validator kiểm độ phủ từ `source_stats` nhúng nên không cần commit nguồn, và index không thể lệch.
- **Giới hạn**: ngưỡng độ phủ chỉ bắt thiếu thô (cả đoạn/cả mục). Vẫn nên đọc đối chiếu 2-3 đoạn mỗi bài trước khi publish.
- Trang chặn bot: tải HTML bằng trình duyệt (`--compressed` nếu cần) rồi dùng `--html FILE`.
