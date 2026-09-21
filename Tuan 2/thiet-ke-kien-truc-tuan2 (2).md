# TÀI LIỆU THIẾT KẾ KIẾN TRÚC — TUẦN 2 (bản 0.5)

**Đề tài:** Bộ nhớ dài hạn cho AI Assistant / LLM Agent — song ngữ Việt · Anh
**Nhóm:** 2 thành viên · Tháng 9–10/2026
**Cập nhật:** 15/09/2026 — kiến trúc phân lớp, xử lý song ngữ; hạ nhất quán xuyên ngữ xuống hướng mở rộng

---

## 0. Định vị và nguyên tắc thiết kế

**Mục tiêu:** một hệ bộ nhớ dài hạn hoàn chỉnh, **dùng được cả tiếng Việt lẫn tiếng Anh**, đánh giá đủ tám năng lực.

"Hoàn chỉnh" nghĩa là mỗi năng lực có một thành phần chịu trách nhiệm, một tuần được phân
công, và một bộ test chứng minh nó chạy — không phải mỗi năng lực đều sâu ở mức nghiên cứu.

### Năm nguyên tắc chi phối mọi quyết định bên dưới

1. **Việc cần chính xác thì đừng giao cho mô hình.** LLM lo ngữ nghĩa (trích fact, ghép
   thuộc tính, tóm tắt). Python lo so sánh, đếm, xếp thứ tự, phán độ mới.
2. **Tách sổ cái khỏi chỉ mục.** SQLite là nguồn sự thật; ChromaDB và BM25 chỉ là chỉ mục
   để tìm nhanh, dựng lại được từ sổ cái bất cứ lúc nào.
3. **Chuẩn hóa ở tầng ghi, không ở tầng đọc.** Mọi thứ cần so sánh — khóa slot, giá trị,
   ngôn ngữ — được đưa về dạng chuẩn ngay khi ghi. Tầng đọc không phải đoán.
4. **Không lưu thứ do chính mô hình sinh ra, trừ khi người dùng xác nhận.** Nếu không, hệ
   sẽ tự củng cố ảo giác của mình qua các phiên.
5. **Mọi lượt đều để lại vết.** Không có nhật ký vết thì tuần 7 không đo được gì.

---

## 1. Tám năng lực bộ nhớ

| # | Năng lực | Benchmark chấm nó | Thành phần đảm nhiệm | Tuần |
|---|---|---|---|---|
| 1 | Trích xuất & nhớ chính xác | LongMemEval IE · BEAM | `FactExtractor` + truy xuất lai | 3 |
| 2 | Suy luận đa phiên | LongMemEval MR · BEAM multi-hop | `QueryPlanner` tách truy vấn con | 5 |
| 3 | Suy luận thời gian | LongMemEval TR · BEAM | Khoảng hiệu lực `valid_from`/`invalidated_at` | 5 |
| 4 | Cập nhật kiến thức | LongMemEval KU · FactConsolidation | Slot + `seq`; ADD/UPDATE/DELETE/NOOP | 4 |
| 5 | Giải quyết mâu thuẫn | BEAM contradiction | Thao tác `CONFLICT` + hàng chờ rà soát | 4 |
| 6 | Biết từ chối | LongMemEval ABS · BEAM | Ngưỡng trên điểm reranker, hiệu chỉnh thực nghiệm | 6 |
| 7 | Tuân theo sở thích | BEAM preference | Ký ức `pinned`, có hạn ngạch riêng trong ngữ cảnh | 5 |
| 8 | Hiểu dài hạn / tóm tắt | BEAM summarization · MAB LRU | `SessionSummarizer` → ký ức episodic | 6 |

### Ngoài phạm vi — ghi nhận làm hướng mở rộng

**Nhất quán xuyên ngữ**: lưu bằng tiếng Việt, hỏi bằng tiếng Anh (và ngược lại) vẫn phải ra
đúng. Không benchmark công khai nào chấm việc này, và nhóm **không đặt mục tiêu làm trong
8 tuần**. Kiến trúc để sẵn chỗ cho nó — cụ thể là trường `text_canon` được lưu ngay từ đầu,
nên nếu sau này muốn bật thì không phải nhập lại dữ liệu. Ba việc ở tầng ghi (mục 3.1–3.3)
vẫn là cốt lõi vì chúng cần cho việc hệ dùng được hai ngôn ngữ, không phải cho năng lực này.

---

## 2. Kiến trúc phân lớp

```
┌──────────────────────────────────────────────────────────────────────────┐
│ L0  GIAO DIỆN        CLI  ·  (tùy chọn) HTTP API                         │
├──────────────────────────────────────────────────────────────────────────┤
│ L1  ĐIỀU PHỐI        LTM Agent — một lượt: đọc → trả lời → ghi           │
├──────────────────────────────────────────────────────────────────────────┤
│ L2  DỊCH VỤ BỘ NHỚ                                                       │
│     Trích xuất │ Chuẩn hóa │ Cập nhật │ Truy xuất │ Lắp ngữ cảnh │ Tóm tắt│
├──────────────────────────────────────────────────────────────────────────┤
│ L3  CHỈ MỤC                                                              │
│     Vector ngữ nghĩa │ BM25 từ khóa │ Sổ slot                            │
├──────────────────────────────────────────────────────────────────────────┤
│ L4  LƯU TRỮ                                                              │
│     SQLite — sổ cái (nguồn sự thật) │ ChromaDB — chỉ mục vector          │
├──────────────────────────────────────────────────────────────────────────┤
│ L5  ADAPTER          LLM │ Embedding │ Reranker                          │
└──────────────────────────────────────────────────────────────────────────┘
       XUYÊN SUỐT:  Ngôn ngữ · Nguồn gốc · Cache · Nhật ký vết
```

### Vì sao tách sổ cái (SQLite) khỏi chỉ mục (Chroma)

Bản 0.3 dùng Chroma làm nơi lưu duy nhất. Có ba vấn đề:

- `max(seq)` phải quét toàn bộ bản ghi qua API của Chroma. Đó là một câu SQL một dòng.
- Không có ràng buộc toàn vẹn: không có khóa ngoại cho `superseded_by`, không có
  ràng buộc "mỗi slot chỉ một bản `active`". Lỗi logic sẽ lọt âm thầm.
- Đổi mô hình embedding là phải nhúng lại toàn bộ. Nếu dữ liệu gốc nằm ở Chroma thì
  việc đó rủi ro; nếu nằm ở SQLite thì chỉ là dựng lại chỉ mục.

Sau khi tách: SQLite giữ bản ghi, quan hệ, nhật ký vết và sổ slot. Chroma và BM25 là chỉ
mục **dẫn xuất** — xóa đi dựng lại được từ SQLite bằng một lệnh. Điều này còn cho phép quét
tham số ở tuần 6 mà không sợ hỏng dữ liệu.

### Các thành phần ở L2

| Thành phần | Vai trò | Gọi LLM? |
|---|---|---|
| `FactExtractor` | Lượt hội thoại → fact có cấu trúc, song ngữ, có phân loại | Có |
| `ValueNormalizer` | Chuẩn hóa giá trị: ngày → ISO, địa danh → dạng chuẩn, cấp độ → hoa | Không (có bảng bí danh) |
| `SlotRegistry` | Sổ slot: ánh xạ tên thuộc tính → slot chuẩn, có cache embedding | Chỉ khi gặp thuộc tính mới |
| `MemoryUpdater` | ADD / UPDATE / DELETE / NOOP / CONFLICT theo `seq` | Không |
| `ProvenanceGate` | Fact từ phía trợ lý ở trạng thái chờ tới khi người dùng xác nhận | Không |
| `QueryPlanner` | Tách câu hỏi phức thành truy vấn con | Có (có bộ lọc rẻ ở trước) |
| `HybridRetriever` | Dense + BM25, hợp nhất bằng RRF, rồi rerank | Không (dùng reranker) |
| `ContextAssembler` | Lắp ngữ cảnh theo hạn ngạch token | Không |
| `SessionSummarizer` | Cô đọng phiên thành ký ức episodic | Có |

---

## 3. Xử lý song ngữ

Ngôn ngữ là mối quan tâm **xuyên suốt**, không phải một tính năng. Mục tiêu trong phạm vi
đồ án là: hệ **dùng được cả tiếng Việt lẫn tiếng Anh** — người dùng nói ngôn ngữ nào cũng
ghi nhớ và trả lời đúng ngôn ngữ đó. Việc *bắc cầu* giữa hai ngôn ngữ (ghi tiếng Việt, hỏi
tiếng Anh) là hướng mở rộng, không phải mục tiêu.

### 3.1. Tầng ghi — dạng chuẩn

Mỗi fact được lưu ở **hai dạng**:

| Trường | Nội dung | Mục đích |
|---|---|---|
| `text` | Đúng câu người dùng nói, nguyên ngôn ngữ gốc | Hiển thị lại, giữ cách diễn đạt của người dùng |
| `text_canon` | Bản tiếng Anh chuẩn hóa của cùng nội dung | So sánh và truy xuất |
| `lang` | `vi` / `en` | Chọn ngôn ngữ trả lời, tách số liệu khi báo cáo |

`text_canon` **không tốn thêm lời gọi LLM**: bộ trích xuất vốn đã đọc lượt hội thoại đó, chỉ
cần yêu cầu nó xuất thêm một trường trong cùng một JSON.

### 3.2. Khóa slot luôn bằng tiếng Anh

Đây là chỗ dễ hỏng âm thầm nhất. Nếu "trình độ tiếng Nhật" sinh khóa `trinh_do_tieng_nhat`
còn "my Japanese level" sinh `japanese_level`, hệ sẽ coi đó là hai thuộc tính khác nhau và
**mất hoàn toàn khả năng phát hiện cập nhật** — mà không báo lỗi gì.

Ba lớp bảo vệ:

1. Prompt trích xuất bắt buộc: khóa luôn là tiếng Anh, snake_case, không dấu.
2. Lớp kiểm tra: khóa chứa ký tự ngoài `[a-z0-9_]` bị từ chối và yêu cầu sinh lại.
3. `SlotRegistry` ghép thuộc tính mới với slot đã có bằng embedding **tên thuộc tính** —
   và vì tên đã là tiếng Anh nên việc ghép này là đơn ngữ, chính xác hơn hẳn.

### 3.3. Chuẩn hóa giá trị

Khóa trung lập ngôn ngữ vẫn chưa đủ — giá trị cũng phải so được:

| Loại | Vấn đề | Cách chuẩn hóa |
|---|---|---|
| Địa danh | "Hà Nội" · "Hanoi" · "HN" | Bảng bí danh, tra trước khi so sánh |
| Ngày tháng | "tháng trước" · "last month" · "8/2026" | Quy về ISO 8601 tại thời điểm ghi |
| Cấp độ, mã | "n4" · "N4" | Viết hoa, bỏ khoảng trắng |
| Tên riêng | "Phong" · "Đặng Tuấn Phong" | Giữ bản dài nhất, bản ngắn thành bí danh |

Không chuẩn hóa thì hệ sẽ báo `UPDATE` trong khi thực ra không có gì đổi — làm hỏng luôn
thang đo "tỉ lệ tự mâu thuẫn".

### 3.4. Tầng đọc — một chỉ mục, mô hình xuyên ngữ

**Trong phạm vi:** một chỉ mục vector duy nhất, nhúng `text_canon` bằng mô hình xuyên ngữ
(BGE-M3). Vì mọi bản ghi đều đã quy về tiếng Anh ở tầng ghi, chỉ mục này **trên thực tế là
đơn ngữ** — chính xác hơn so với dựa vào khả năng bắc cầu của mô hình, mà vẫn phục vụ được
người dùng nói cả hai thứ tiếng.

**Mở rộng, chưa làm:** thêm một chỉ mục thứ hai nhúng `text` gốc-ngữ rồi hợp nhất hai danh
sách bằng RRF. Việc này chỉ cần khi muốn tối ưu riêng trường hợp câu hỏi khác ngôn ngữ so
với lúc ghi — tức là phục vụ năng lực đã bị đưa ra ngoài phạm vi.

### 3.5. Tầng trả lời

Ngôn ngữ trả lời = ngôn ngữ của lượt hiện tại, trừ khi người dùng đã đặt chỉ dẫn quy trình
("từ giờ trả lời tiếng Anh nhé") — chỉ dẫn đó được lưu thành ký ức `procedural` và luôn nạp
vào system prompt. Bản thân system prompt viết bằng tiếng Anh, vì mô hình tuân theo chỉ dẫn
tiếng Anh ổn định hơn.

### 3.6. Vì sao phần này vẫn là cốt lõi dù đã bỏ năng lực xuyên ngữ

LongMemEval, BEAM, FactConsolidation **đều là tiếng Anh**. Nếu hệ chỉ chạy tiếng Việt thì
phải tự dịch benchmark hoặc tự xây hết, và sẽ bị hỏi "số này so với ai". Hệ dùng được cả hai
ngôn ngữ chạy thẳng được benchmark chuẩn — đó là lý do giữ mục 3.1 đến 3.3 trong phạm vi,
độc lập với việc có làm năng lực xuyên ngữ hay không.

---

## 4. Đường truy xuất

Đây là phần được thiết kế lại nhiều nhất so với bản 0.3.

```
câu hỏi
  │
  ├─► QueryPlanner ──► [q, q1, q2]            (chỉ khi câu hỏi phức)
  │
  ├─► Dense: chỉ mục ngữ nghĩa    ─┐
  │                                ├─► RRF ──► ~30 ứng viên
  ├─► BM25 từ khóa                ─┘
  │
  ├─► Reranker (cross-encoder)    ──► xếp lại, điểm hiệu chỉnh tốt hơn
  │
  ├─► Lọc bản cũ: status=active, rồi gom theo slot giữ max(seq)
  │
  ├─► ContextAssembler: pinned (hạn ngạch riêng) + top-k + tóm tắt phiên
  │
  └─► ngữ cảnh ≤ ngân sách token   +   tín hiệu từ chối
```

### Vì sao thêm BM25 bên cạnh vector

Vector tìm theo nghĩa nhưng **trượt các chuỗi chính xác**: "N4", "E22TTNT", tên riêng, mã
số. Đây đúng là loại thông tin mà bộ nhớ cá nhân hay lưu. BM25 bắt chính xác chuỗi. Với
tiếng Việt lợi ích còn lớn hơn vì chất lượng embedding yếu hơn tiếng Anh. Hợp nhất bằng
Reciprocal Rank Fusion — không cần chỉnh trọng số, chỉ dựa vào thứ hạng.

### Vì sao thêm reranker

Bi-encoder (embedding) nhúng câu hỏi và ký ức **độc lập**, nên nó chỉ đo độ giống chung
chung. Cross-encoder đọc **cặp** (câu hỏi, ký ức) cùng lúc nên phân biệt được "liên quan"
với "chỉ cùng chủ đề". Hai cái lợi:

- Độ chính xác truy xuất tăng rõ, nhất là với câu hỏi đa bước.
- **Điểm của reranker hiệu chỉnh tốt hơn nhiều so với cosine** — mà năng lực 6 (biết từ
  chối) chính là đặt một ngưỡng lên điểm này. Đặt ngưỡng lên cosine gần như không dùng được
  vì cosine của hai câu bất kỳ đã nằm quanh 0,7–0,8.

Chi phí: reranker chạy trên ~30 ứng viên, không phải toàn kho, nên thêm khoảng vài chục ms
trên CPU. Chấp nhận được, và sẽ đo ở tuần 7.

### `ContextAssembler` — ngân sách token

Không nạp "top-k" một cách mù quáng, mà chia hạn ngạch:

| Hạng mục | Hạn ngạch gợi ý | Ghi chú |
|---|---|---|
| Ký ức `pinned` (sở thích, ràng buộc, quy trình) | ~25% | Luôn có mặt, cắt theo `seq` mới nhất nếu tràn |
| Ký ức semantic đã rerank | ~55% | Phần chính |
| Tóm tắt phiên liên quan | ~20% | Chỉ khi câu hỏi mang tính hồi tưởng |

Nhờ có hạn ngạch, trục chi phí trở thành một tham số điều khiển được chứ không phải một hệ
quả ngẫu nhiên — và so sánh giữa các cấu hình mới hợp lệ.

---

## 5. Lược đồ bộ nhớ

Mỗi ký ức là một **slot**: `(subject, attribute) → value`, kèm số thứ tự đơn điệu `seq`.

| Nhóm | Trường | Phục vụ |
|---|---|---|
| Nhận dạng | `subject` · `attribute` (luôn tiếng Anh) · `value` · `value_canon` | 1, 9 |
| Văn bản | `text` (gốc ngữ) · `text_canon` (tiếng Anh) · `lang` | 1, 9 |
| Độ mới | `seq` · `status` · `superseded_by` | 4, 5 |
| Thời gian | `valid_from` · `invalidated_at` · `event_time` | 3, 8 |
| Phân loại | `memory_type` (semantic/preference/episodic/procedural) · `pinned` | 7, 8 |
| Nguồn gốc | `speaker` (user/assistant) · `confirmed` · `needs_review` | 5, và nguyên tắc 4 |
| Truy vết | `session_id` · `turn_id` · `source_text` (không nhúng) | debug |

`status` có bốn giá trị: `active` · `pending` · `superseded` · `deleted`.

**`pending` là giá trị mới.** Fact trích từ lượt của **trợ lý** vào trạng thái `pending` và
không được truy xuất, cho tới khi người dùng xác nhận ở lượt sau. Lý do ở mục 6 dưới.

---

## 6. Trích xuất từ cả hai phía hội thoại

LongMemEval có hẳn một loại câu hỏi tên `single-session-assistant`: thông tin do trợ lý nói
ra mà người dùng cần nhớ. Bỏ phía trợ lý là mất trọn một nhóm điểm.

Nhưng hai phía không được đối xử như nhau:

| Nguồn | Xử lý | Lý do |
|---|---|---|
| Lượt **người dùng** | `status = active` ngay | Người dùng nói về chính mình |
| Lượt **trợ lý** | `status = pending`, chờ xác nhận | Nếu lưu vô điều kiện, hệ ghi lại chính thứ mô hình vừa bịa, rồi lượt sau truy xuất chúng như sự thật đã xác lập — **ảo giác tự củng cố qua các phiên** |

Xác nhận được ghi nhận khi: người dùng nhắc lại thông tin đó, hoặc trả lời đồng ý, hoặc
dùng nó trong câu hỏi tiếp theo. Quá 3 lượt không ai nhắc lại thì bản `pending` bị bỏ.

Đây là một luật kiến trúc, không phải tiểu tiết — nó là thứ ngăn hệ thống tự đầu độc theo
thời gian, và là điểm đáng nêu khi báo cáo.

---

## 7. Công nghệ — toàn bộ miễn phí

| Thành phần | Lựa chọn | Lý do |
|---|---|---|
| Ngôn ngữ | Python 3.11 | Hệ sinh thái |
| LLM | **Gemini 2.5 Flash — gói miễn phí** | ~1.500 lượt/ngày, ~15 lượt/phút, không cần thẻ |
| LLM dự phòng | Groq free tier · Ollama local | Khi đụng hạn mức, và để đo phương sai theo mô hình nền |
| Embedding | **BGE-M3** chạy local | Xuyên ngữ, ngữ cảnh 8192 token, hỗ trợ tiếng Việt tốt |
| Embedding so sánh | `multilingual-e5-base` · `vietnamese-bi-encoder` | Thí nghiệm tuần 6 |
| Reranker | **`bge-reranker-v2-m3`** chạy local | Cross-encoder đa ngữ, miễn phí |
| Chỉ mục từ khóa | BM25 (`rank_bm25`) | Bắt chuỗi chính xác |
| Sổ cái | **SQLite** | Nguồn sự thật, ràng buộc toàn vẹn, nhật ký vết |
| Chỉ mục vector | ChromaDB | `pip install` là chạy, có metadata filter |
| Kiểm thử | pytest + LLM giả lập | Offline, không tốn hạn mức, lặp lại được |

### Vì sao embedding và reranker chạy local

Không phải để tiết kiệm tiền, mà vì **cấu trúc lời gọi**. LLM được gọi ~2 lần mỗi lượt.
Embedding được gọi cho mỗi fact, mỗi truy vấn con, mỗi lần ghép slot, và **mỗi lần quét
tham số**. Một lần quét ngưỡng trên 200 câu × 10 giá trị là hàng nghìn lời gọi — đặt lên API
là đốt sạch hạn mức 1.500 lượt/ngày trong một buổi chiều.

### Ghi chú về token — quan trọng khi báo cáo

Token là **mảnh từ con**, không phải từ cũng không phải câu. Tiếng Anh khoảng 0,75 token
mỗi từ; tiếng Việt bị cắt nát hơn nhiều vì dấu thanh không nằm trong từ vựng gốc — cùng một
nội dung thường tốn **khoảng gấp đôi** token.

Hệ quả: **không được so token/truy vấn giữa bộ test tiếng Việt và benchmark tiếng Anh**.
Phải báo cáo tách riêng theo `lang`. Nhóm sẽ đo tỉ lệ thật bằng tokenizer của chính mô hình
đang dùng và đưa con số vào báo cáo, thay vì trích quy ước chung chung.

Lưu ý thêm: vector DB **không lưu token**. Nó lưu một vector độ dài cố định — câu 5 chữ hay
50 chữ đều ra vector cùng kích thước. Token chỉ ảnh hưởng (a) giới hạn đầu vào của mô hình
embedding, (b) ngân sách prompt.

### Lưu gì vào kho vector

**Không lưu hội thoại nguyên văn.** Ba thứ được lưu, ba mục đích:

| Lưu gì | Có nhúng không | Để làm gì |
|---|---|---|
| Fact đã trích (dạng slot) | Có — hai chỉ mục | Năng lực 1–7, 9 |
| Tóm tắt phiên (1–3 câu) | Có | Năng lực 8 |
| `source_text` — lượt gốc | **Không**, chỉ nằm trong SQLite | Truy vết khi debug |

---

## 8. Kế hoạch đánh giá

### Ba trục, áp cho cả tám năng lực

| Trục | Thang đo |
|---|---|
| Độ chính xác | Accuracy **tách theo từng loại câu hỏi và theo `lang`**, chấm bằng LLM-as-a-Judge với mô hình chấm và prompt chấm công bố kèm |
| Tính nhất quán | Tỉ lệ dùng đúng fact sau cập nhật · tỉ lệ tự mâu thuẫn · tỉ lệ từ chối đúng lúc · tỉ lệ tôn trọng ràng buộc đã ghi nhớ |
| Hiệu năng | p50/p95 tách theo pha (dense · BM25 · rerank · sinh) · token mỗi truy vấn **tách theo ngôn ngữ** · số bản ghi |

### Năm cấu hình đối chứng

| Cấu hình | Cắt bỏ gì | Chứng minh điều gì |
|---|---|---|
| `full-context` | toàn bộ lớp bộ nhớ | Baseline trên; chi phí token và điểm tụt khi lịch sử dài |
| `dense-only` | BM25 + reranker | Đóng góp của truy xuất lai |
| `no-rerank` | reranker | Đóng góp của cross-encoder, nhất là với năng lực 6 |
| `llm-judge` | `max(seq)`, để LLM tự chọn bản mới | Đóng góp của cơ chế cập nhật tất định |
| `ours` | — | Hệ đầy đủ, so trên cả tám năng lực |

Mọi cấu hình cố định **cùng mô hình nền – cùng k – cùng ngân sách token**.

### Dữ liệu

- **LongMemEval-S** — chính, phủ 5 năng lực, tiếng Anh.
- **FactConsolidation** — năng lực 4 và 5.
- **BEAM** mức 128K — đối chiếu các năng lực còn lại (không chạy mức 10M).
- **Bộ test tiếng Việt tự xây** — 150–200 câu, sinh bằng script.

### Nhật ký vết

Mỗi lượt ghi một dòng JSONL vào SQLite: truy vấn con, ứng viên từng chỉ mục, điểm trước và
sau rerank, ký ức được nạp, thao tác bộ nhớ, token, độ trễ từng pha. Không có cái này thì
tuần 7 không phân tích được vì sao một câu sai.

---

## 9. Phạm vi thực thi — cốt lõi, nên có, mở rộng

Kiến trúc trên là bản đầy đủ. Thực thi chia ba mức để không vỡ tiến độ. Mức **mở rộng**
được viết ra để kiến trúc không bị bịt đường, **không phải để làm** — nếu bị hỏi, trả lời rõ
là nhóm chủ động để ngoài phạm vi:

| Mức | Hạng mục | Ghi chú |
|---|---|---|
| **Cốt lõi** (bắt buộc xong) | Sổ cái SQLite · slot + `seq` · ADD/UPDATE/DELETE/NOOP · dense một chỉ mục · `ContextAssembler` · nhật ký vết · CLI | Đủ để chạy LongMemEval-S |
| **Nên có** (mục tiêu chính) | BM25 + RRF · reranker · `CONFLICT` · `pending` hai phía · ký ức pinned · tóm tắt phiên · `QueryPlanner` · chuẩn hóa khóa và giá trị cho hai ngôn ngữ | Đây là phần tạo ra đóng góp |
| **Mở rộng** (KHÔNG đặt mục tiêu) | **Chỉ mục kép + năng lực nhất quán xuyên ngữ và bộ test của nó** · quét tham số 3 mô hình embedding · HTTP API · ký ức procedural | Chỉ đụng tới khi mọi thứ ở hai mức trên đã xong |

---

## 10. Lộ trình 8 tuần

| Tuần | Nội dung | Năng lực |
|---|---|---|
| 1 | Nghiên cứu nền tảng, đặt vấn đề, phạm vi | — |
| 2 | Rà soát benchmark · khung 8 năng lực · kiến trúc phân lớp · chốt công nghệ | — |
| 3 | Sổ cái SQLite + chỉ mục dense; pipeline chạy đầu–cuối; nhật ký vết | 1 |
| 4 | Slot + `seq`; ADD/UPDATE/DELETE/NOOP/CONFLICT; cổng nguồn gốc `pending` | 4, 5 |
| 5 | BM25 + hợp nhất RRF; `QueryPlanner`; khoảng hiệu lực; ký ức pinned | 2, 3, 7 |
| 6 | Reranker; hiệu chỉnh ngưỡng từ chối; tóm tắt phiên; bộ test tiếng Việt | 6, 8 |
| 7 | Chạy 5 cấu hình × 3 trục; phân tích lỗi từ nhật ký vết; tối ưu; hoàn thiện demo | tất cả |
| 8 | Báo cáo, tài liệu, đóng gói mã nguồn, trình bày cuối | — |

---

## 11. Rủi ro

| Rủi ro | Ảnh hưởng | Xử lý |
|---|---|---|
| Khóa slot lẫn hai ngôn ngữ | Mất khả năng phát hiện cập nhật, **lỗi im lặng** | Ba lớp bảo vệ ở mục 3.2; thêm một test riêng kiểm tra khóa luôn là ASCII |
| LLM đặt tên thuộc tính không ổn định | Cùng thuộc tính tách thành 2 slot | `SlotRegistry` ghép bằng embedding tên thuộc tính (ngưỡng 0,82); dự phòng là từ điển slot cố định; quét ngưỡng 0,70–0,95 ở tuần 6 |
| Tám năng lực quá rộng cho 8 tuần | Không năng lực nào đủ sâu | Bảng phạm vi ở mục 9 định sẵn thứ tự cắt; nhất quán xuyên ngữ đã chủ động để ngoài phạm vi |
| Reranker làm chậm | Trục hiệu năng xấu đi | Chỉ rerank ~30 ứng viên; đo riêng pha rerank; có cấu hình `no-rerank` để so |
| Hạn mức Gemini thay đổi | Gián đoạn thí nghiệm | Adapter cho phép đổi sang Groq/Ollama trong một file |
| Chấm bằng LLM không ổn định | Kết quả không tin được | Công bố mô hình chấm và prompt chấm; chấm tay một mẫu 50 câu để đối chiếu |
| Dữ liệu gói miễn phí bị dùng để huấn luyện | Vấn đề riêng tư | Chỉ dùng dữ liệu tự sinh và benchmark công khai, không dùng dữ liệu cá nhân thật |

---

## Tài liệu tham khảo

- Wu et al., *LongMemEval*, ICLR 2025, arXiv:2410.10813
- Hu et al., *MemoryAgentBench*, ICLR 2026, arXiv:2507.05257
- Tavakoli et al., *BEAM / LIGHT*, ICLR 2026, arXiv:2510.27246
- Maharana et al., *LoCoMo*, ACL 2024, arXiv:2402.17753
- Chhikara et al., *Mem0*, ECAI 2025, arXiv:2504.19413
- Reddy & Challaram, *Don't Ask the LLM to Track Freshness*, arXiv:2606.01435 (2026)
- Jiang et al., *Anatomy of Agentic Memory*, arXiv:2602.19320 (2026)
- Hu et al., *Memory in the Age of AI Agents*, arXiv:2512.13564 (2026)
- Zhang et al., *Survey on the Memory Mechanism of LLM-based Agents*, ACM TOIS 2025, DOI 10.1145/3748302
- Zheng et al., *LLM-as-a-Judge*, NeurIPS 2023, arXiv:2306.05685
- Cormack et al., *Reciprocal Rank Fusion*, SIGIR 2009 — cơ sở cho bước hợp nhất kết quả
