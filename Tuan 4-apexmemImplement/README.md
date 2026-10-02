# apexmem — Bộ nhớ dài hạn cho LLM Agent theo APEX-MEM

Tái hiện **APEX-MEM** (Banerjee et al., *Agentic Semi-Structured Memory with Temporal Reasoning
for Long-Term Conversational AI*, ACL 2026, arXiv:2604.14362) và đánh giá trên **LongMemEval-S**
(5 năng lực IE · MR · TR · KU · ABS), LLM là **GPT-5.5 qua 9router**, chỉ tiếng Anh.

```
LUỒNG GHI (mỗi câu hỏi một đồ thị)                       LUỒNG ĐỌC
haystack ~50 phiên                                       câu hỏi + question_date
  │ 1. lọc liên quan  (dense BGE-M3 + BM25 → RRF, top-10)    │
  │ 2. trích xuất     (LLM: sự kiện + fact có thời gian)     ▼
  │ 3. giải quyết     (LLM chỉ khi mơ hồ: thực thể/thuộc tính)  Agent ReAct (≤ 20 bước)
  │ 4. ghi append-only                                        SchemaViewer · EntityLookup
  ▼                                                           GraphSQL · Search · PropertySearch
SQLite: 7 bảng đồ thị + FTS5  ◄──── công cụ chỉ-đọc ─────────┘
chỉ mục vector = dẫn xuất (tính từ SQLite + cache embedding)      → câu trả lời → LLM-as-a-Judge
```

## Cấu trúc

| Đường dẫn | Vai trò | Bài báo |
|---|---|---|
| `ltm/store/schema.sql`, `graphdb.py` | Đồ thị thuộc tính 7 bảng, append-only bằng trigger, GraphSQL chỉ-đọc 3 lớp chặn | §3.1, §4.3 |
| `ltm/store/vector.py`, `search.py` | Chỉ mục vector dẫn xuất + tìm kiếm lai dense/FTS5 hợp nhất RRF | §4 (Search) |
| `ltm/memory/relevance.py` | Lọc phiên liên quan trước khi dựng | §online construction |
| `ltm/memory/extractor.py` | Hội thoại → sự kiện + fact (kiểm tra kiểu bằng Python) | §3.2 |
| `ltm/memory/resolver.py` | choose_existing / propose_new / none; gộp thuộc tính | §3.3 |
| `ltm/memory/builder.py` | Ghép luồng ghi, ghi nhật ký vết | Hình 1 |
| `ltm/agent/tools.py` | 5 công cụ | §4, Bảng 3 |
| `ltm/agent/react.py` | Vòng ReAct (function calling hoặc JSON) | §4 |
| `ltm/baselines/simple_search.py` | Baseline SimpleSearch K = V (RAG thường), top-5 phiên | LongMemEval |
| `ltm/eval/` | nạp dữ liệu, chia dev/test, judge chính thức, chạy, báo cáo, phân loại lỗi | |
| `ltm/demo/chat.py` | Trợ lý trò chuyện có bộ nhớ thật (nhớ qua các lần mở) | |
| `ltm/demo/export_html.py` | Xuất kết quả thành 1 file HTML — xem được trên máy không có Python | |
| `ltm/check.py` | Kiểm tra 9router, model, dữ liệu, cache | |
| `kaggle/embed_longmemeval.py` | **Phần duy nhất cần GPU**: nhúng sẵn toàn bộ LongMemEval-S | |
| `docs/HUONG-DAN-9ROUTER.md` | Cài 9router, nhiều tài khoản, lưu ý tính hợp lệ số liệu | |

## Cài đặt (Windows, PowerShell)

```powershell
cd Samsung-Agent\apexmem
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env          # điền NINEROUTER_API_KEY (xem docs/HUONG-DAN-9ROUTER.md)
python -m pytest                # ~100 test, chạy offline bằng LLM giả, ~5 giây
```

## Chuẩn bị dữ liệu

1. **Dữ liệu:** `python -m ltm.eval.download` → `data/longmemeval/longmemeval_s_cleaned.json`.
   (Notebook tuần 2 dùng `longmemeval_s.json` bản gốc; question_id giống nhau. Muốn dùng bản gốc thì
   đổi `eval.dataset_path` — nhưng khi đó phải nhúng trên Kaggle từ CÙNG file đó.)
2. **Embedding trên Kaggle (GPU):** mở `kaggle/embed_longmemeval.py`, làm theo phần đầu file
   (Accelerator = GPU T4, Internet = ON, Run All, ~20–30 phút). Tải `embed_cache.db` về
   `data/cache/embed_cache.db`.
   Không có file này hệ vẫn chạy, nhưng sẽ nhúng ~500 lượt/câu hỏi trên CPU (rất chậm).
3. **Chia dev/test:** tự động ở lần chạy đầu, **cùng thuật toán và seed với notebook 01** → ra đúng
   150 câu dev cũ. Có sẵn `split.json` từ notebook thì chép vào `data/splits/split.json`.
4. **Hiệu chỉnh bộ lọc phiên (không tốn lời gọi LLM, chỉ cần cache Kaggle):**
   `python -m ltm.eval.calibrate_filter` → quét top-k và ngưỡng cosine trên tập dev, in luật rẻ nhất
   giữ đủ phiên bằng chứng ở ≥ 95% câu, kèm đoạn `filter:` để dán vào `config.yaml`.
5. **Kiểm tra:** chạy `9router` ở một cửa sổ khác, rồi `python -m ltm.check`.

## Chạy đánh giá

```powershell
# 1. Thử nhỏ trước — đo chi phí thật
python -m ltm.eval.run --config full --split dev --n 20 --workers 1 --progress

# 2. Ablation theo Bảng 3 của bài báo — DÙNG LẠI đồ thị đã dựng, chỉ tốn lời gọi trả lời
python -m ltm.eval.run --config a1 --split dev --n 20          # SchemaViewer + EntityLookup
python -m ltm.eval.run --config a2 --split dev --n 20          # + GraphSQL + PropertySearch
python -m ltm.eval.run --config simple_search_kv --split dev --n 20 # baseline LongMemEval (K = V), không dựng đồ thị
python -m ltm.eval.run --config steps10 --split dev --n 20     # giới hạn 10 bước (có steps40)

# 3. Bảng so sánh + file demo HTML
python -m ltm.eval.report data\runs\full\dev data\runs\a1\dev data\runs\a2\dev data\runs\simple_search_kv\dev
python -m ltm.demo.export_html data\runs\full\dev data\runs\a1\dev -o demo.html
```

- Bị ngắt giữa chừng (hết hạn mức, tắt máy) → chạy lại **đúng lệnh cũ**: câu đã xong được bỏ qua,
  mọi lời gọi LLM đã làm nằm trong `data/cache/llm_cache.db`, không tốn lại hạn mức.
- `--build-only` chỉ dựng đồ thị (chạy qua đêm), `--qtype temporal-reasoning` lọc theo loại,
  `--trials 3` chấm 3 lần như bài báo.
- Mỗi câu một file `data/graphs/<chữ ký>/<qid>.db` — mở bằng DB Browser for SQLite để soi. Bảng
  `trace` ghi từng phiên được dựng: số fact, lý do fact bị loại, quyết định giải quyết thực thể.
- `data/runs/<config>/<split>/results.jsonl`: mọi bước agent, recall, chi phí từng pha;
  `hypotheses.jsonl` đúng định dạng script chấm gốc của LongMemEval.

### Báo cáo sinh ra những gì

1. Accuracy theo **6 loại câu hỏi**, nhóm **_abs**, 5 năng lực, micro và macro.
2. **Truy xuất:** recall của bộ lọc phiên; recall phiên mà công cụ của agent chạm tới → tách lỗi
   "không tìm thấy" khỏi lỗi "suy luận sai".
3. **Chi phí:** số lần gọi công cụ, lời gọi LLM, token pha dựng / pha trả lời, độ trễ p50/p95.
4. **Phân loại câu sai tự động:** `filtered_out` · `not_extracted` · `tool_miss` · `sql_error` ·
   `reasoning` · `abstention_fail` (nhầm thực thể cần soi tay).
5. **Mô hình thực sự phục vụ** — phát hiện 9router lén đổi model.

## Demo trò chuyện

```powershell
python -m ltm.demo.chat --db data\chat\demo.db
```

Kịch bản gợi ý cho KU: `/date 2024-01-10` → "I just passed JLPT N5" → `/date 2024-06-01` →
"I passed N4 last week" → "What's my Japanese level now? What was it before?" → `/me` để xem cả hai
phiên bản cùng tồn tại (append-only) và agent chọn bản mới nhất lúc đọc.

Máy công ty không chạy được Python → dùng file `demo.html` (xuất ở trên), mở bằng trình duyệt.

## Chỗ khác bài báo (ghi rõ khi báo cáo)

| Điểm | Bài báo | Ở đây | Lý do |
|---|---|---|---|
| Trích xuất | 1 lượt / lời gọi, Claude Sonnet 4.5 | ≤ 6 lượt / lời gọi, GPT-5.6 Luna | Hạn mức; `extract.turns_per_call: 1` để làm đúng như bài |
| Giải quyết | LLM cho mọi nhắc tới, Claude Haiku 4.5 | LLM chỉ khi mơ hồ (trùng tên → dùng lại; không ứng viên → tạo mới) | Giảm số lời gọi (đo thực tế ở mục Chi phí) |
| Ontology | 35 lớp (26 nêu trong bài) | 26 lớp của bài + 9 lớp nhóm tự thêm | Nên thay bằng danh sách ở Phụ lục I của bài (`TEAM_ONTOLOGY` trong `graphdb.py`) |
| Công cụ | 4 | 4 + PropertySearch | Bài có số liệu nhưng không mô tả |
| Số bước tối đa | 40 | 20 (có preset 10 / 40) | Bài cho thấy gần chạm trần ở ~20 |
| Ngưỡng lọc phiên | Θ_rel = 0,2 (không nêu mô hình/thang điểm) | ngưỡng trên cosine BGE-M3, hiệu chỉnh trên dev (`calibrate_filter`) | Không chép được 0,2 sang thang điểm khác |
| Lượt gốc phiên bị lọc | không lưu | vẫn lưu + nhúng cho Search | Lưới an toàn cho recall; `filter.store_all_turns: false` để làm đúng như bài |
| Embedding | không nêu | BGE-M3 | Dùng lại số đo tuần 2 |

Mọi khác biệt đều là tham số trong `config.yaml` → có thể chạy lại đúng cấu hình của bài để so.
