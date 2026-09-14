# TÀI LIỆU THIẾT KẾ KIẾN TRÚC — TUẦN 2

**Đề tài:** Bộ nhớ dài hạn cho AI Assistant / LLM Agent
**Nhóm:** 2 thành viên · Tháng 9–10/2026
**Phiên bản:** 0.2 — 14/09/2026

---

## 0. Thay đổi so với tuần 1 (sau phản hồi mentor)

| Hạng mục | Tuần 1 | Tuần 2 |
|---|---|---|
| Benchmark chính | LoCoMo | **LongMemEval-S** (có nhóm câu hỏi *knowledge-update*) |
| Benchmark cho trục cập nhật | không có | **FactConsolidation** (MemoryAgentBench, ICLR 2026) |
| Trọng tâm đóng góp | "làm một hệ bộ nhớ" | **Cơ chế cập nhật & giải quyết xung đột tất định** |
| Nguồn tham chiếu | MemGPT (2023) làm nguồn định nghĩa | Survey 2026, BEAM/MemoryAgentBench (ICLR 2026); MemGPT chỉ là mốc lịch sử |

**Lý do đổi trọng tâm.** Trên FactConsolidation, các hệ thống mạnh vẫn hỏng ở đúng
tình huống N5→N4: Zep/Graphiti ~7%, HippoRAG-v2 ~54%, GPT-4o full-context ~60%
(Reddy & Challaram, arXiv:2606.01435, 2026). Đây là khoảng trống thật, đủ hẹp để
nhóm 2 người làm xong trong 2 tháng, và đủ đo đếm được để viết báo cáo.

---

## 1. Kiến trúc tổng thể

```
┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐   ┌──────────────┐
│  Giao diện   │⇄  │  LTM Agent   │⇄  │   Memory Manager     │⇄  │  Vector DB   │
│  (CLI/Web)   │   │  điều phối   │   │  4 pha bộ nhớ        │   │  (Chroma)    │
└──────────────┘   └──────┬───────┘   └──────────┬───────────┘   └──────────────┘
                          │                      │
                   ┌──────┴──────┐    ┌──────────┼──────────┬────────────┐
                   │ LLM Adapter │    │ Extractor│ Updater  │ Retriever  │
                   │ openai/mock │    │  pha 1   │  pha 2   │   pha 3    │
                   └─────────────┘    └──────────┴──────────┴────────────┘
```

**Nguyên tắc tách lớp.** LLM và Vector DB đều nằm sau một interface trừu tượng
(`LLMClient`, `VectorStore`). Đổi từ OpenAI sang Gemini, hay Chroma sang Qdrant,
chỉ là viết thêm một file adapter — không đụng vào `memory/`. Điều này cần thiết
vì phần đánh giá sẽ phải chạy lại cùng một cơ chế bộ nhớ trên nhiều LLM nền để
kiểm soát biến "phương sai theo backbone" mà *Anatomy of Agentic Memory*
(arXiv:2602.19320, 2026) cảnh báo.

### 1.1. Công nghệ đã chốt

| Thành phần | Lựa chọn | Lý do |
|---|---|---|
| Ngôn ngữ | Python 3.11 | Hệ sinh thái sẵn |
| LLM | OpenAI `gpt-4o-mini` | Rẻ, là baseline phổ biến nhất trong các paper → số liệu so sánh được |
| Embedding | `text-embedding-3-small` | 1536 chiều, rẻ, đủ tốt cho tiếng Việt |
| Vector DB | **ChromaDB** (persist đĩa, cosine) | `pip install` là chạy; có metadata filter — cần cho `status=active` |
| Test | pytest + LLM giả lập | Chạy CI offline, không tốn tiền, kết quả tất định |

---

## 2. Lược đồ bộ nhớ

Mỗi ký ức là một **slot**:

```
(subject, attribute) ──> value
   "user"   "trinh_do_tieng_nhat"   "N4"
```

| Trường | Kiểu | Vai trò |
|---|---|---|
| `subject` | str | Thực thể sở hữu fact |
| `attribute` | str | Khóa slot đã chuẩn hóa (không dấu, snake_case) |
| `value` | str | Giá trị hiện tại |
| `text` | str | Câu tự nhiên — đây là thứ được nhúng embedding |
| **`seq`** | int | **Số thứ tự đơn điệu toàn cục — nguồn sự thật duy nhất về độ mới** |
| `status` | enum | `active` / `superseded` / `deleted` |
| `superseded_by` | str? | Trỏ tới bản đã thay thế nó → dựng lại được dòng lịch sử |
| `valid_from`, `invalidated_at` | ISO | Khoảng hiệu lực → phục vụ câu hỏi suy luận thời gian |
| `memory_type` | enum | `semantic` / `episodic` / `procedural` |
| `session_id`, `turn_id` | | Truy vết về lượt hội thoại gốc |

**Vì sao dùng slot thay vì chuỗi fact rời rạc?** Mem0 lưu fact dưới dạng câu tự do, nên
để biết "N5" và "N4" nói về cùng một thứ thì phải nhờ LLM so sánh. Khóa slot làm việc
phát hiện xung đột trở thành một phép tra khóa — nhanh, tất định, và không sai.

---

## 3. Vòng lặp bộ nhớ 4 pha

### Pha 1 — Trích xuất (LLM)

Đầu vào: một lượt hội thoại. Đầu ra: danh sách `{subject, attribute, value, text, negated}`.
LLM được chỉ thị: chỉ rút thông tin **bền vững**, không suy diễn, `attribute` phải ổn định
giữa các lần gọi.

### Pha 2 — Cập nhật (Python quyết định)

**Đây là phần đóng góp chính.** Thuật toán:

```
1. Ghép slot:
     nếu tồn tại slot trùng khóa chính xác  -> dùng slot đó
     ngược lại: nhúng tên thuộc tính, so cosine với các slot đang active
                nếu sim >= 0.82 -> coi là cùng slot (xử lý trường hợp đồng nghĩa)
                ngược lại       -> tạo slot mới

2. Lấy bản đang hiệu lực: current = argmax(seq) trong các bản active của slot

3. Quyết định:
     fact.negated  và current tồn tại  -> DELETE
     current is None                   -> ADD
     normalize(current.value) == normalize(fact.value) -> NOOP
     ngược lại                         -> UPDATE

4. Thi hành UPDATE:
     bản mới:  seq = next_seq(),  status = active
     bản cũ :  status = superseded,  invalidated_at = now,  superseded_by = id_mới
```

**Điểm mấu chốt:** bước 3 và 4 **không gọi LLM**. LLM chỉ tham gia bước 1 (ghép ngữ nghĩa)
và chỉ ở trường hợp khóa không trùng chính xác. Đây chính là công thức mà
arXiv:2606.01435 chứng minh: tách "ghép cặp" (cần ngữ nghĩa → LLM) khỏi "phán độ mới"
(cần chính xác → Python), thay vì trộn cả hai vào một prompt.

**Bản cũ không bị xóa.** Chuyển sang `superseded` để giữ lại dòng lịch sử
`N5 → N4 → N3`. Cần cho hai việc: (a) trả lời câu hỏi suy luận thời gian
("hồi tháng 5 trình độ tôi là gì?"), (b) truy vết khi debug sai sót.

### Pha 3 — Truy xuất

```
1. Nhúng câu hỏi
2. Tìm top-(3k) trong kho, LỌC status = active ngay ở tầng truy vấn
3. Bỏ các bản có sim < τ  (mặc định 0.25)
4. Gom theo slot, mỗi slot chỉ giữ bản seq lớn nhất
5. Sắp theo sim, lấy top-k (mặc định k = 5)
```

Bước 4 nhìn thừa nhưng **không thừa**: embedding của "trình độ tiếng Nhật N5" và
"trình độ tiếng Nhật N4" gần như trùng nhau, nên top-k rất dễ trả về cả hai, và khi
prompt chứa hai fact mâu thuẫn thì LLM đoán bừa. Đây đúng là kiểu lỗi mà
FactConsolidation nhắm vào.

### Pha 4 — Sinh phản hồi

Ký ức được chèn vào prompt kèm số `seq`, với chỉ thị: ký ức đã cho là bản mới nhất đã
được xác thực, hãy tin nó; nếu thiếu thông tin thì nói thẳng là chưa biết (phục vụ
trục *abstention*).

---

## 4. Kế hoạch đánh giá

### 4.1. Ba trục đo

| Trục | Thang đo | Cách lấy |
|---|---|---|
| Độ chính xác | Accuracy theo từng loại câu hỏi, LLM-as-a-Judge | LongMemEval-S |
| Tính nhất quán | **Tỉ lệ dùng đúng fact sau cập nhật**, tỉ lệ tự mâu thuẫn, tỉ lệ abstention đúng | FactConsolidation + bộ test tiếng Việt tự xây |
| Hiệu năng | p50/p95 (tách pha truy xuất và tổng), token/truy vấn, `\|M\|` | Đo sẵn trong `Turn` và `LLMClient.stats()` |

### 4.2. Các cấu hình sẽ so sánh

| Ký hiệu | Mô tả | Dùng để chứng minh |
|---|---|---|
| `full-context` | Nhồi toàn bộ lịch sử vào prompt | Baseline trên, cho thấy chi phí token |
| `rag-only` | RAG thuần, không có ADD/UPDATE/DELETE | Cho thấy truy xuất đơn thuần không giải được bài toán cập nhật |
| `llm-judge-freshness` | Có slot, nhưng để LLM tự chọn bản mới | **Cấu hình đối chứng cho đóng góp chính** |
| `ours` | Slot + `max(seq)` tất định | Cấu hình đề xuất |

Mọi cấu hình phải cố định **cùng LLM – cùng k – cùng ngân sách token**, nếu không thì
con số không nói lên điều gì.

### 4.3. Bộ test tiếng Việt tự xây

Theo đúng khuôn FactConsolidation, tự sinh bằng script:

- **Đơn bước (`fact_sh`):** 1 thuộc tính có 2–5 phiên bản theo thời gian, hỏi giá trị hiện tại.
  Ví dụ: `trinh_do_tieng_nhat: N5 → N4 → N3`, hỏi "trình độ tiếng Nhật của tôi giờ là gì?"
- **Đa bước (`fact_mh`):** câu hỏi phải nối 2 slot, cả hai đều đã bị cập nhật.
  Ví dụ: "tìm lớp học phù hợp gần nhà tôi" — cần cả `trinh_do_tieng_nhat` (đã đổi)
  và `noi_o` (đã đổi).
- **Nhiễu:** chèn 6K / 32K / 64K token hội thoại không liên quan giữa các lần cập nhật,
  để đo xem độ chính xác có tụt theo độ dài lịch sử không.
- Quy mô mục tiêu: 150–200 câu, đủ để báo cáo có sai số chấp nhận được.

---

## 5. Rủi ro và cách xử lý

| Rủi ro | Ảnh hưởng | Cách xử lý |
|---|---|---|
| LLM đặt tên `attribute` không ổn định giữa các lần gọi | Cùng một thuộc tính bị tách thành 2 slot → phát hiện xung đột thất bại | Ghép slot bằng embedding tên thuộc tính (ngưỡng 0.82); nếu vẫn lệch thì bổ sung từ điển slot cố định cho các thuộc tính hay gặp |
| Ngưỡng ghép slot quá cao / quá thấp | Gộp nhầm 2 thuộc tính khác nhau, hoặc bỏ sót xung đột | Quét tham số 0.70–0.95 ở tuần 6, báo cáo đường cong |
| Chi phí API vượt dự trù | Không chạy hết thí nghiệm | `gpt-4o-mini` + cache embedding; LLM giả lập cho toàn bộ test |
| Embedding tiếng Việt yếu | Truy xuất trượt | So `text-embedding-3-small` với một mô hình đa ngữ nguồn mở ở tuần 6 |
| Thiếu thời gian | Không xong 8 tuần | Bộ test tiếng Việt và knowledge graph là hạng mục cắt được đầu tiên |

---

## 6. Đã hoàn thành trong tuần 2

- Kiến trúc module với interface tách rời LLM và vector DB
- Lược đồ `MemoryRecord` dạng slot + `seq`
- Vòng lặp 4 pha chạy được đầu–cuối
- Cơ chế ADD / UPDATE / DELETE / NOOP + lưu lịch sử slot
- Truy xuất có hai lớp lọc bản cũ
- CLI tối thiểu (`chat` / `show` / `history` / `reset`)
- 8 test tự động chạy offline — **tất cả đều đạt**, trong đó có test đúng kịch bản N5 → N4 → N3

## 7. Việc của tuần 3

1. Thay LLM giả lập bằng `gpt-4o-mini` thật, đo p50/p95 và token/truy vấn
2. Viết script tải và chạy LongMemEval-S, lấy số trên nhóm câu hỏi *knowledge-update*
3. Dựng cấu hình đối chứng `llm-judge-freshness` để có số so sánh cho đóng góp chính
4. Cache embedding ra đĩa để chạy lại thí nghiệm không tốn tiền

---

## Tài liệu tham khảo

- Wu et al., *LongMemEval*, ICLR 2025, arXiv:2410.10813
- Hu et al., *Evaluating Memory in LLM Agents via Incremental Multi-Turn Interactions* (MemoryAgentBench), ICLR 2026, arXiv:2507.05257
- Tavakoli et al., *Beyond a Million Tokens* (BEAM / LIGHT), ICLR 2026, arXiv:2510.27246
- Reddy & Challaram, *Don't Ask the LLM to Track Freshness*, arXiv:2606.01435 (2026)
- Chhikara et al., *Mem0*, ECAI 2025, arXiv:2504.19413
- Jiang et al., *Anatomy of Agentic Memory*, arXiv:2602.19320 (2026)
- Hu et al., *Memory in the Age of AI Agents*, arXiv:2512.13564 (2026)
- Zhang et al., *A Survey on the Memory Mechanism of LLM-based Agents*, ACM TOIS 2025, DOI 10.1145/3748302
