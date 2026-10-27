# Slow Reads pipeline — nguồn, dịch, xuất bản

Pipeline tách việc lấy nguồn, dịch và đăng bài thành ba chặng độc lập. Mục tiêu: bot tìm nguồn (Grok) **không phải tái tạo nguyên văn** nội dung có bản quyền, nên không bị giới hạn "chỉ trích dẫn ngắn"; bản dịch do Claude thực hiện từ file nguồn; Grok chỉ chạy lệnh kiểm tra và publish.

```
Grok (discovery)        scripts/fetch_source.py        Claude (translate)         Grok (publish)
URL + metadata   ──►    source.txt + meta.json   ──►   articles/<id>.json   ──►    validate + commit + push
(không body)            (.cache, không commit)        + source_stats (số đo)      (không đọc body)
```

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

## Chạy tay

```bash
pip install -r scripts/requirements.txt      # Windows: python -m pip ...
python3 scripts/fetch_source.py "https://example.com/essay" --id ten-bai   # Windows: python
# Claude ghi slow-reads/articles/ten-bai.json từ source.txt
python3 scripts/attach_source_stats.py ten-bai
python3 scripts/validate_slow_read.py slow-reads/articles/ten-bai.json
python3 scripts/add_slow_read.py
python3 scripts/validate_slow_read.py --strict
```

- `--html FILE`: trích từ HTML đã lưu (khi trang chặn tải trực tiếp hoặc cần lưu bằng trình duyệt).
- `--favor-recall`: giữ nhiều chữ hơn, đổi lại có thể lẫn boilerplate.
- `--force`: ghi đè cache nguồn đã có.
- `--no-cache`: bỏ qua đối chiếu cache, dùng `source_stats` nhúng (giống CI).
- `--strict`: warning thành lỗi; CI dùng cờ này.
- `attach_source_stats.py --coverage condensed <id>`: chỉ dùng cho bài lược dịch cũ; mặc định `full`.

## Chính sách độ phủ

- `full` (mặc định cho bài mới): CI fail nếu bản dịch dưới **45% ký tự** hoặc **50% số câu** của nguồn.
- `condensed`: cho bài lược dịch cũ/được chủ ý rút gọn; các chỉ số chỉ ghi chú, schema vẫn bắt buộc.
- Chỉ số blocks/headings chỉ ghi chú vì việc gộp đoạn và tách câu khác nhau theo ngôn ngữ.
- Khi có cache, validator còn đối chiếu `sha256`; trên CI chỉ dùng `source_stats` nhúng, không cần nguồn.
- Giới hạn: ngưỡng chỉ bắt thiếu thô (cả đoạn/cả mục). Không thay thế việc đọc đối chiếu thủ công.

## Prompt cho bot

Ba khối dưới đây copy nguyên văn vào bot. Chỗ `<...>` là biến cần điền.

### 1. Grok — discovery

```text
VAI TRÒ: DISCOVERY cho thư viện Slow Reads của Daily News.
Bạn KHÔNG dịch, KHÔNG tóm tắt, KHÔNG trích nguyên văn nội dung bài. Bạn chỉ trả URL và metadata.

Đầu vào: <số bài cần / chủ đề ưu tiên / ngày>
Đầu ra: CHỈ một JSON array, không markdown, không giải thích:
[
  {
    "url": "https://...",
    "title": "tiêu đề gốc",
    "author": "tên tác giả hoặc \"\"",
    "source": "tên trang",
    "lang": "en",
    "topics_guess": ["Tư duy & khoa học"],
    "reason": "một câu vì sao đáng dịch"
  }
]

Quy tắc:
- Bài dài (từ 700 từ), công khai, không paywall, không cần đăng nhập.
- topics_guess chọn từ: Con người, Tình yêu, Sự nghiệp, Đối nhân xử thế, Tiền bạc, Tâm lý, Tư duy & khoa học, Stoicism.
- Không bịa title/author. Không rõ thì để "".
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

Nhiệm vụ: dịch TOÀN BỘ sang tiếng Việt và ghi đúng một file
slow-reads/articles/<id>.json. Không in toàn bộ body ra chat; dùng công cụ ghi file.

Quy tắc nội dung:
- Dịch đủ 100%, không lược đoạn, không thêm bình luận, không thay bằng tóm tắt.
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
python3 scripts/attach_source_stats.py <id>
python3 scripts/validate_slow_read.py slow-reads/articles/<id>.json
Sửa đến khi 0 error. Với coverage mặc định "full", warning dưới 45% ký tự hoặc 50% số câu nghĩa là đã bỏ sót — phải dịch bù.
Không đặt --coverage condensed để né cảnh báo; chỉ dùng khi bài đã được chủ ý lược dịch.
Báo cáo: đường dẫn file, số block, số từ, coverage chars/blocks/sentences, kết quả validate.
```

### 3. Grok — publish

```text
VAI TRÒ: PUBLISH cho thư viện Slow Reads của Daily News.
Bạn nhận một file slow-reads/articles/<id>.json đã dịch và validate xong.
Bạn KHÔNG đọc/in nội dung body, KHÔNG sửa bản dịch, KHÔNG dịch lại.

Chạy tuần tự, dừng ngay nếu một lệnh thất bại:
1. python3 scripts/validate_slow_read.py slow-reads/articles/<id>.json
2. python3 scripts/add_slow_read.py
3. python3 scripts/validate_slow_read.py --strict
4. git add slow-reads/articles/<id>.json slow-reads/articles/index.json
5. git commit -m "Add Slow Reads article <id>"
6. git push origin main

Nếu bước 1-3 báo lỗi: dừng, gửi nguyên văn lỗi cho người dịch. Không tự sửa nội dung, không tự thêm/sửa source_stats, không đặt coverage "condensed" để né cảnh báo.

Sau khi push, xác minh:
- git rev-parse HEAD và git rev-parse origin/main giống nhau.
- Workflow "Deploy GitHub Pages" chạy xanh (chờ 1-2 phút nếu cần).
- Mở https://hexdino.github.io/DailyNews/slow-reads/articles/index.json và xác nhận có "id": "<id>".

Báo cáo cuối: commit SHA, tổng số bài trong index, URL live của thư viện, lỗi còn tồn (nếu có).
```

## Lưu ý

- **Không commit nội dung nguồn**: `.cache/` đã nằm trong `.gitignore`. Chỉ bản dịch lên repo.
- **Bản quyền**: dịch toàn văn và đăng công khai là tác phẩm phái sinh. Chỉ làm với nguồn cho phép hoặc chấp nhận rủi ro; ghi rõ tác giả/nguồn và link gốc.
- **CI** chạy `add_slow_read.py` + `validate_slow_read.py --strict` trước khi deploy. Validator kiểm độ phủ từ `source_stats` nhúng nên không cần commit nguồn, và index không thể lệch.
- **Giới hạn**: ngưỡng độ phủ chỉ bắt thiếu thô (cả đoạn/cả mục). Vẫn nên đọc đối chiếu 2-3 đoạn mỗi bài trước khi publish.
- Trang chặn bot: tải HTML bằng trình duyệt (`--compressed` nếu cần) rồi dùng `--html FILE`.
