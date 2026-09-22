# BÁO CÁO & KẾ HOẠCH TUẦN 3 — SỔ CÁI VÀ PIPELINE ĐẦU–CUỐI

**Đề tài:** Bộ nhớ dài hạn cho AI Assistant / LLM Agent
**Nhóm:** 2 thành viên · Tuần 3/8 · 21/09/2026
**Năng lực nhắm tới:** #1 — Trích xuất & nhớ chính xác

---

## 1. Chốt lại từ tuần 2

Tuần 2 đã khóa các quyết định sau, và nhóm không mở lại trong tuần 3:

| Quyết định | Nội dung |
|---|---|
| Khung năng lực | 8 năng lực, mỗi năng lực gắn một benchmark, một thành phần, một tuần |
| Kiến trúc | 6 lớp; **tách kho ký ức (SQLite) khỏi chỉ mục (Chroma, BM25)** |
| Song ngữ | Chuẩn hóa ở tầng ghi: `text` / `text_canon` / `lang`; khóa slot luôn tiếng Anh |
| Truy xuất | dense + BM25 → RRF → reranker → lọc `max(seq)` → lắp ngữ cảnh theo hạn ngạch |
| Nguồn gốc | Fact từ lượt trợ lý vào `pending`, chờ người dùng xác nhận |
| Công nghệ | Gemini 2.5 Flash (miễn phí) · BGE-M3 local · bge-reranker-v2-m3 · SQLite + Chroma |
| Đánh giá | 3 trục × 5 cấu hình đối chứng, cùng mô hình nền – cùng k – cùng ngân sách token |
| Ngoài phạm vi | Nhất quán xuyên ngữ — chủ động để làm hướng mở rộng |

Ngoài tài liệu thiết kế, nhóm đã có **ba notebook trên LongMemEval-S** (thư mục `DataExplore`):
01 khảo sát cấu trúc và chia dev/test, 02 nhúng BGE-M3, 03 đo Recall@k của vector, BM25 và RRF
trên tập dev. Đó là cơ sở để tuần 3 viết loader chuẩn thay vì đọc dữ liệu thủ công trong notebook.

**Việc còn nợ:** khung mã nguồn. Hết tuần 2 nhóm có thiết kế và dữ liệu, chưa có gì chạy được.

---

## 2. Mục tiêu tuần 3

Dựng **đường mỏng nhưng thông suốt**: nạp hội thoại → trích fact → ghi vào kho → nhúng →
truy xuất → trả lời → chấm điểm. Chưa có slot/seq logic, chưa BM25, chưa reranker — mỗi thứ
đó có tuần của nó. Mục tiêu tuần này là **con số đầu tiên** và **hạ tầng để mọi tuần sau
dựa vào**.

### Định nghĩa "xong"

Một lệnh chạy được, ra bảng số:

```
python -m ltm.eval.run --config dense-only --dataset longmemeval_s --split dev --n 100
```

Kèm ba điều kiện:

1. Bảng accuracy **tách theo loại câu hỏi**, không phải một con số gộp.
2. Mọi lượt để lại một dòng trong nhật ký vết — truy lại được vì sao câu số 47 sai.
3. `pytest` xanh toàn bộ, chạy offline bằng LLM giả lập, không tốn hạn mức.

---

## 3. Phần làm kỹ nhất tuần này: kho ký ức *(đã xong)*

Nhóm chọn làm **một module thật sâu** thay vì dựng đủ mọi file ở mức sơ sài. Module đó là
kho ký ức, vì ba lý do:

1. **Đây là nơi duy nhất không được phép sai.** Chroma trả nhầm một ứng viên thì reranker
   còn vớt lại; kho ký ức ghi sai một bản `active` thì mọi thứ phía sau sai và không có cách
   nào biết.
2. **Không gọi LLM** nên test được 100% offline, không đụng hạn mức Gemini.
3. Toàn bộ logic cập nhật của tuần 4 chỉ là các phép ghi lên đúng bảng này. Schema đúng từ
   bây giờ thì **tuần 4 không phải nhập lại dữ liệu**.

### 3.1. Hợp đồng với tầng chỉ mục

> Chroma chỉ lưu `id` + vector + vài metadata để lọc.
> Nội dung đưa cho LLM **luôn** được nạp lại từ kho ký ức qua `get_by_ids()`.

Nhờ vậy chỉ mục và kho ký ức không bao giờ bất đồng về nội dung — cùng lắm là chỉ mục cũ, và
`rebuild` sửa được. Đây là điều kiện để tuần 6 quét tham số embedding mà không sợ hỏng dữ liệu.

### 3.2. Bốn chi tiết dễ hỏng âm thầm, đã xử lý

| Chi tiết | Nếu làm sai | Cách làm |
|---|---|---|
| `PRAGMA foreign_keys` | Mặc định **TẮT** trong SQLite → `superseded_by` trỏ vào id không tồn tại vẫn ghi được | Bật cho từng kết nối trong `_configure()`, không đặt trong file `.sql` |
| Cấp phát `seq` | `SELECT max(seq)+1` bị cấp trùng khi chạy hai tiến trình eval song song | `UPDATE counter SET value=value+1 RETURNING value` — nguyên tử |
| Thứ tự `get_by_ids` | `WHERE id IN (...)` trả theo rowid → **xóa sạch thứ hạng của reranker**, không báo lỗi | Sắp lại theo đúng thứ tự đầu vào |
| `json.dumps` | Mặc định `ensure_ascii=True` → mọi vết tiếng Việt thành `ạ...`, không đọc nổi lúc debug | `ensure_ascii=False` |

### 3.3. Lọc bản cũ bằng SQL, không bằng LLM

Đúng nguyên tắc 1 của bản thiết kế. Một câu window function thì tất định và giải thích được:

```sql
SELECT * FROM (
  SELECT *, ROW_NUMBER() OVER (PARTITION BY subject, attribute ORDER BY seq DESC) AS rn
  FROM memory WHERE status = 'active'
) WHERE rn = 1
```

Phương án nhờ LLM "chọn bản mới nhất" chính là cấu hình đối chứng `llm-judge` ở tuần 7 —
nhóm sẽ đo chênh lệch chứ không khẳng định suông.

### 3.4. Ràng buộc của tuần 4, cố ý chưa bật

```sql
CREATE UNIQUE INDEX ux_active_slot ON memory(subject, attribute) WHERE status='active';
```

Tuần 3 chỉ có thao tác ADD. Nạp LongMemEval, một người nói N5 rồi sau nói N4 sẽ sinh hai
bản `active` cùng slot — đúng như thiết kế, vì `MemoryUpdater` chưa tồn tại. Bật ràng buộc
bây giờ là tự làm vỡ pipeline. Tuần 4, sau khi có UPDATE, chạy đúng một dòng trên; từ lúc
đó mọi lỗi logic cập nhật **nổ ngay tại chỗ** thay vì âm thầm làm hỏng số liệu. Đã có sẵn
một test chứng minh ràng buộc bắt đúng lỗi.

### 3.5. Kết quả kiểm thử

16 test, xanh toàn bộ, chạy 0,9 giây, không gọi mạng. Mỗi test tương ứng một bất biến đã
cam kết trong tài liệu kiến trúc — test hỏng nghĩa là kiến trúc bị vi phạm, không phải lỗi vặt:

- `seq` tăng đơn điệu và duy nhất
- fact từ lượt trợ lý vào `pending`, **không lọt vào chỉ mục**, xác nhận xong mới hiện
- mỗi slot chỉ trả về bản `max(seq)`, loại `deleted`
- khóa `trình_độ_tiếng_nhật` bị từ chối với lý do `attribute_not_ascii`; `2nd_language` và
  `Japanese Level` bị từ chối với lý do `attribute_bad_format`
- mọi lần từ chối đều vào nhật ký vết → ra thẳng **tỉ lệ khóa hỏng** cho báo cáo
- chỉ mục nhúng `text_canon` (tiếng Anh) nhưng metadata vẫn giữ `lang='vi'`

---

## 4. Kế hoạch thực thi chi tiết

Cấu trúc thư mục mục tiêu cuối tuần — **11 file mã nguồn**, không hơn:

```
ltm/
  config.py          config.yaml
  adapters/  llm.py   embed.py   fake.py
  store/     schema.sql ✅  ledger.py ✅  vector.py
  memory/    extractor.py   assembler.py
  agent.py
  eval/      datasets.py   judge.py   run.py
tests/       test_ledger.py ✅  test_extractor.py  test_pipeline.py
```

---

### NGÀY 1 — Khung repo và adapter *(người A)*

**Làm gì**

1. `pip install google-genai sentence-transformers chromadb pyyaml pytest` → ghim vào
   `requirements.txt` bằng `pip freeze`, ghim luôn phiên bản BGE-M3.
2. `config.py` + `config.yaml` — **mọi tham số ở một chỗ**, không rải hằng số trong code:

```yaml
llm:      {provider: gemini, model: gemini-2.5-flash, temperature: 0.0, max_retries: 2}
embed:    {model: BAAI/bge-m3, device: cpu, batch_size: 32, cache: true}
retrieve: {top_k: 10, n_candidates: 30}
context:  {token_budget: 2000, quota: {pinned: 0.25, semantic: 0.55, summary: 0.20}}
paths:    {db: data/ltm.db, chroma: data/chroma}
```

3. `adapters/llm.py` — một giao diện duy nhất, để tuần 6 đổi sang Groq/Ollama chỉ sửa một file:

```python
class LLMAdapter(Protocol):
    def complete_json(self, prompt: str, schema: dict) -> dict: ...
    def complete_text(self, prompt: str) -> str: ...
```

   Bên trong `GeminiAdapter`: `temperature=0` (bắt buộc — eval phải lặp lại được),
   `response_mime_type="application/json"`, retry có backoff khi gặp 429.

4. `adapters/embed.py` — bọc BGE-M3, **có cache ngay từ đầu**:

```python
def encode(self, texts: list[str]) -> np.ndarray:
    # tra bảng cache theo sha1(text); chỉ nhúng phần chưa có; ghi lại
```

   Bảng cache là một file SQLite riêng `data/embed_cache.db`, cột `(hash, model, vector BLOB)`.
   Có `model` trong khóa để tuần 6 quét 3 mô hình embedding không lẫn cache của nhau.

5. `adapters/fake.py` — `FakeLLM` trả JSON cố định theo kịch bản, để test chạy offline.

**Xong khi:** `python -c "from ltm.config import cfg; print(cfg.llm.model)"` chạy được, và
`FakeLLM().complete_json(...)` trả đúng JSON đã cài.

---

### NGÀY 2–3 — `FactExtractor` *(người A)*

Đây là thành phần **duy nhất gọi LLM ở tầng ghi**, nên chất lượng của nó quyết định trần
điểm của cả hệ. Một lời gọi cho mỗi lượt, xuất tất cả trường trong cùng một JSON —
`text_canon` không tốn thêm lời gọi vì mô hình vốn đã đọc lượt đó rồi.

**Prompt (viết bằng tiếng Anh — mô hình tuân chỉ dẫn tiếng Anh ổn định hơn)**

```
You extract durable facts from one conversation turn.

Rules:
- `attribute` MUST be English snake_case ASCII, even when the turn is Vietnamese.
  "trình độ tiếng Nhật" -> japanese_level.  Never transliterate.
- `text` = the original sentence, unchanged, in its original language.
- `text_canon` = the same content in normalized English.
- `value_canon`: dates -> ISO 8601 using TODAY={today}; places -> canonical English
  name (Hà Nội -> Hanoi); codes -> uppercase, no spaces (n4 -> N4).
- Extract only durable facts about the speaker. Skip small talk, questions,
  and anything true for just this moment.
- Return {"facts": []} if there is nothing durable. An empty list is a correct answer.

Turn (speaker={speaker}): {text}
```

**Mã**

```python
class FactExtractor:
    def extract(self, text: str, *, speaker: str, today: str) -> tuple[list[Fact], dict]:
        # 1. cache: sha1(text|speaker) -> JSON đã trích. Chạy lại eval KHÔNG gọi lại LLM.
        # 2. gọi complete_json với schema cứng
        # 3. dựng Fact; fact nào validate() != None -> retry MỘT lần với thông báo lỗi
        #    kèm trong prompt, sau đó bỏ và ghi vào trace
        # 4. trả (facts, meta) với meta = {n_llm_calls, retried, latency_ms, tokens}
```

**Cache là bắt buộc, không phải tối ưu.** LongMemEval-S có hàng trăm phiên; không cache thì
mỗi lần chạy lại eval là đốt hết hạn mức 1.500 lượt/ngày và sẽ không ai dám chạy lại thí nghiệm.

**Test (`test_extractor.py`, dùng `FakeLLM`)**

- JSON hợp lệ → ra đúng số `Fact`, đúng trường
- `attribute` tiếng Việt → retry một lần → vẫn sai → bị bỏ + có dòng trace
- LLM trả JSON hỏng → không làm sập pipeline, trả danh sách rỗng + trace
- gọi `extract` hai lần cùng một câu → lời gọi LLM thứ hai **không xảy ra** (cache)

**Xong khi:** trích tay 20 lượt (10 Việt, 10 Anh), soi bằng mắt, tỉ lệ khóa đúng ≥ 90%.
Con số này vào báo cáo.

---

### NGÀY 3–4 — Chỉ mục và trả lời *(người B)*

1. **`store/vector.py`** — bọc Chroma, ba hàm:

```python
def upsert(items: list[dict]) -> None        # nhận đúng định dạng iter_for_index()
def query(text: str, k: int, where: dict | None = None) -> list[tuple[int, float]]
def rebuild(ledger: Ledger) -> int           # xóa collection, nạp lại từ kho ký ức
```

   `rebuild()` phải viết ngay ngày đầu, không để sau: nó là thứ chứng minh chỉ mục đúng là
   dẫn xuất. Có nó rồi thì đổi mô hình embedding ở tuần 6 chỉ là một lệnh.

2. **`memory/assembler.py`** — bản tuần 3 rất đơn giản nhưng **đã chia hạn ngạch**:

```python
def assemble(pinned, semantic, summaries, budget: int) -> tuple[str, dict]:
    # cắt theo hạn ngạch trong config; đếm token bằng tokenizer của chính mô hình
    # đang dùng, KHÔNG dùng quy ước "1 token ≈ 0.75 từ"
```

   Trả kèm `dict` thống kê token từng hạng mục — đây là trục chi phí trong báo cáo.

3. **`agent.py`** — một lượt, ba bước, có đo giờ từng pha:

```python
def ingest_turn(text, speaker, session_id, turn_id) -> IngestResult
def answer(question, session_id) -> tuple[str, dict]
    # retrieve -> ledger.get_by_ids -> assemble -> LLM -> log_trace('answer', ...)
```

**Xong khi:** một kịch bản tay chạy thông — nạp 3 lượt tiếng Việt, hỏi lại, trả lời đúng,
và `SELECT * FROM trace` có đủ 4 dòng.

---

### NGÀY 4–5 — Bộ đánh giá *(người A)*

1. **`eval/datasets.py`** — chuyển logic từ notebook khảo sát thành loader chuẩn. Với
   LongMemEval-S, mỗi mẫu cần lấy: `question_id`, `question_type`, `question`, `answer`,
   `question_date`, danh sách phiên trong haystack kèm ngày của từng phiên, và
   `answer_session_ids` (để tuần 7 đo cả recall của truy xuất, không chỉ accuracy).

```python
@dataclass
class EvalCase:
    qid: str; qtype: str; question: str; gold: str
    sessions: list[tuple[str, list[dict]]]   # (ngày, các lượt)
    answer_session_ids: list[str]
```

   Loader trả iterator, **không nạp cả bộ vào RAM**.

2. **`eval/judge.py`** — LLM-as-a-Judge. Prompt chấm chốt luôn tuần này, không sửa về sau:

```
Question: {q}
Reference answer: {gold}
System answer: {pred}
Is the system answer correct? Consider it correct if it conveys the same
information as the reference, even with different wording.
Answer with exactly one word: CORRECT or INCORRECT.
```

   `temperature=0`. Lưu nguyên văn phán quyết vào trace để tuần 7 đối chiếu với chấm tay.

3. **`eval/run.py`** — vòng chạy:

```
với mỗi case:  ledger + chroma rỗng  ->  nạp toàn bộ haystack  ->  hỏi  ->  chấm  ->  trace
in bảng: accuracy theo qtype | p50/p95 từng pha | token theo lang | #fact, #slot
```

   Mỗi case một file DB riêng trong `data/runs/{config}/{qid}.db`, để phân tích lại từng
   case mà không phải chạy lại.

**Xong khi:** lệnh ở mục 2 chạy hết 100 case và in ra bảng.

---

### NGÀY 5–6 — Chạy và phân tích lỗi *(cả hai)*

Chạy `--n 100`, rồi **ngồi đọc 10 câu sai đầu tiên**. Đây là phần tạo ra nội dung báo cáo,
không phải phần phụ. Ba câu SQL dùng để soi:

```sql
-- Sai vì không trích được fact, hay vì trích được mà không tìm ra?
SELECT json_extract(payload,'$.qid'), json_extract(payload,'$.retrieved_ids')
FROM trace WHERE kind='answer' AND json_extract(payload,'$.verdict')='INCORRECT';

-- Những khóa slot nào bị từ chối nhiều nhất -> sửa prompt trích xuất
SELECT json_extract(value,'$.reason'), COUNT(*) FROM trace,
  json_each(json_extract(payload,'$.rejected')) WHERE kind='ingest' GROUP BY 1;

-- Pha nào chậm nhất
SELECT kind, AVG(total_ms) FROM trace GROUP BY kind;
```

Phân loại mỗi câu sai vào đúng một nhóm: **trích thiếu · truy xuất trượt · lắp ngữ cảnh
cắt nhầm · sinh sai**. Bảng phân loại này là thứ quyết định tuần 4–6 ưu tiên sửa gì.

---

### NGÀY 7 — Chốt số và báo cáo *(cả hai)*

Điền bảng ở mục 5, viết 1 trang, kèm bảng phân loại lỗi.

---

## 5. Số sẽ báo cáo cuối tuần

| Số | Vì sao đo từ tuần 3 |
|---|---|
| Accuracy theo từng loại câu hỏi của LongMemEval-S | Là đường cơ sở; mọi cải tiến tuần sau so với nó |
| Tỉ lệ khóa slot bị từ chối, tách theo lý do | Đo trực tiếp chất lượng prompt trích xuất |
| Số fact / lượt hội thoại, số slot phân biệt | Biết kho lớn cỡ nào trước khi bàn tới tối ưu |
| p50/p95 tách pha: trích xuất · nhúng · truy xuất · sinh | Tuần 6 thêm reranker mới có cái để so |
| Token mỗi truy vấn, **tách theo `lang`** | Tiếng Việt tốn khoảng gấp đôi token; gộp lại là số vô nghĩa |
| Phân loại 10 câu sai đầu tiên | Quyết định thứ tự ưu tiên của tuần 4–6 |

---

## 6. Ba bẫy nhóm tự đặt ra để tránh

1. **Không làm slot/seq logic trong tuần 3.** Cám dỗ rất lớn vì schema đã có sẵn cột. Làm
   sớm thì tuần 4 không còn gì để đo và phần cập nhật sẽ hời hợt.
2. **Cache embedding và cache trích xuất ngay từ ngày đầu.** Không có cache thì mỗi lần chạy
   lại 100 câu là nhúng và trích lại từ đầu, mất cả buổi, và sẽ không ai dám chạy lại thí nghiệm.
3. **Chốt mô hình chấm và prompt chấm ngay tuần 3, không để tới tuần 7.** Đổi prompt chấm
   giữa chừng là mọi số đo trước đó phải bỏ.

---

## 7. Rủi ro của riêng tuần 3

| Rủi ro | Xử lý |
|---|---|
| Hạn mức Gemini 1.500 lượt/ngày hết giữa lúc chạy eval | Cache trích xuất theo `sha1(lượt)`; chạy lại eval không gọi lại LLM |
| LongMemEval-S có phiên rất dài, trích xuất chậm | Tuần 3 chạy 100 câu trước; đo tốc độ rồi mới quyết mở rộng |
| BGE-M3 tải model lần đầu nặng | Tải sẵn về máy, ghim phiên bản trong `requirements.txt` |
| Hai người sửa cùng một file | Kho ký ức và extractor tách hẳn hai thư mục; giao diện giữa chúng là dataclass `Fact`, đã cố định từ ngày 2 |

---

## 8. Câu hỏi muốn hỏi anh

1. Tuần 3 nhóm chạy 100 câu LongMemEval-S để lấy đường cơ sở. Anh thấy nên mở rộng lên cả
   bộ ngay, hay giữ 100 câu cho tới khi có đủ reranker ở tuần 6 rồi mới chạy toàn bộ?
2. Cấu hình đối chứng `llm-judge` (để LLM tự chọn bản mới nhất thay cho `max(seq)`) — anh
   thấy có đáng dành thời gian chạy không, hay coi cơ chế tất định là hiển nhiên đúng và
   bỏ cấu hình đó đi?
