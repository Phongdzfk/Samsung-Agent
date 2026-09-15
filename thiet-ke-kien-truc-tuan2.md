# TÀI LIỆU THIẾT KẾ KIẾN TRÚC — TUẦN 2 (bản 0.3)

**Đề tài:** Bộ nhớ dài hạn cho AI Assistant / LLM Agent
**Nhóm:** 2 thành viên · Tháng 9–10/2026
**Cập nhật:** 15/09/2026 — sửa định vị phạm vi và chốt lại công nghệ miễn phí

---

## 0. Định vị đề tài

**Mục tiêu: một hệ bộ nhớ dài hạn hoàn chỉnh, đánh giá đủ tám năng lực.**

"Hoàn chỉnh" ở đây không có nghĩa là mỗi năng lực đều sâu ở mức nghiên cứu — với 8 tuần và
2 người thì không khả thi. Nó có nghĩa là: **mỗi năng lực đều có một thành phần chịu trách
nhiệm, một tuần được phân công, và một bộ test chứng minh nó chạy.**

Cơ chế cập nhật tất định (slot + `seq`) là chi tiết kỹ thuật làm cho hai trong tám năng lực
đạt kết quả tốt — không phải luận điểm của cả đồ án.

### Thay đổi so với bản 0.2

| Hạng mục | Bản 0.2 | Bản 0.3 |
|---|---|---|
| Định vị | "Cơ chế cập nhật tất định" là đóng góp chính | Hệ hoàn chỉnh, 8 năng lực; cập nhật là 1 trong 8 |
| Lộ trình tuần 3–8 | Xoay quanh trục cập nhật | Mỗi tuần gắn một nhóm năng lực cụ thể |
| LLM | OpenAI `gpt-4o-mini` (trả phí) | **Gemini 2.5 Flash — gói miễn phí** |
| Embedding | `text-embedding-3-small` (trả phí) | **Mô hình tiếng Việt chạy local** (sentence-transformers) |

---

## 1. Tám năng lực bộ nhớ

| # | Năng lực | Benchmark chấm nó | Thành phần trong hệ thống | Tuần |
|---|---|---|---|---|
| 1 | Trích xuất & nhớ chính xác | LongMemEval IE · BEAM | `FactExtractor` + truy xuất top-k theo embedding | 3 |
| 2 | Suy luận đa phiên | LongMemEval MR · BEAM multi-hop | `QueryPlanner` tách câu hỏi thành truy vấn con | 5 |
| 3 | Suy luận thời gian | LongMemEval TR · BEAM | Khoảng hiệu lực `valid_from` / `invalidated_at` | 5 |
| 4 | Cập nhật kiến thức | LongMemEval KU · FactConsolidation | Slot + `seq`; ADD / UPDATE / DELETE / NOOP | 4 |
| 5 | Giải quyết mâu thuẫn | BEAM contradiction resolution | Thao tác `CONFLICT`, đánh dấu `needs_review` | 4 |
| 6 | Biết từ chối | LongMemEval ABS · BEAM | Ngưỡng tin cậy τ, hiệu chỉnh bằng thực nghiệm | 6 |
| 7 | Tuân theo sở thích | BEAM preference following | Ký ức `pinned` — luôn nạp, không qua top-k | 5 |
| 8 | Hiểu dài hạn / tóm tắt | BEAM summarization · MemoryAgentBench LRU | Cô đọng mỗi phiên thành một ký ức `episodic` | 6 |

**Vì sao năng lực 7 cần cơ chế riêng.** Câu "gợi ý cho tôi vài món ăn nhẹ" không hề giống
câu "tôi bị dị ứng đậu phộng" về mặt ngữ nghĩa. Nếu chỉ dựa vào top-k, ràng buộc dị ứng sẽ
không bao giờ được nạp vào ngữ cảnh. Vì vậy ký ức loại `preference` và `procedural` được
đánh dấu `pinned` và nạp trong mọi lượt, không phụ thuộc độ tương đồng.

**Vì sao năng lực 2 cần cơ chế riêng.** Câu hỏi "tìm lớp tiếng Nhật phù hợp gần nhà mình"
cần hai mẩu ký ức nằm ở hai phiên khác nhau. Embedding của cả câu thường chỉ nằm gần một
trong hai, nên truy xuất một lần sẽ trượt mẩu còn lại.

---

## 2. Kiến trúc tổng thể

```
┌──────────────┐   ┌──────────────┐   ┌──────────────────────┐   ┌──────────────┐
│  Giao diện   │⇄  │  LLM Agent   │⇄  │  Bộ quản lý bộ nhớ   │⇄  │  Kho vector  │
│  CLI         │   │  điều phối   │   │  4 pha               │   │  ChromaDB    │
└──────────────┘   └──────┬───────┘   └──────────┬───────────┘   └──────────────┘
                          │                      │
                   ┌──────┴──────┐    ┌──────────┼──────────┬────────────┐
                   │ LLM Adapter │    │ Extractor│ Updater  │ Retriever  │
                   │ gemini/mock │    │  pha 1   │  pha 2   │   pha 3    │
                   └─────────────┘    └──────────┴──────────┴────────────┘
                                         + QueryPlanner  + SessionSummarizer
```

**Nguyên tắc tách lớp.** LLM và kho vector đều nằm sau interface trừu tượng
(`LLMClient`, `VectorStore`). Đổi Gemini sang mô hình khác, hay Chroma sang Qdrant, chỉ là
thêm một file adapter. Đây là yêu cầu của phần đánh giá chứ không phải sở thích kỹ thuật:
khảo sát *Anatomy of Agentic Memory* (arXiv:2602.19320, 2026) chỉ ra kết quả mảng này có
phương sai rất lớn theo mô hình nền, nên phải chạy được cùng một cơ chế trên nhiều LLM.

---

## 3. Công nghệ — toàn bộ miễn phí

| Thành phần | Lựa chọn | Lý do |
|---|---|---|
| Ngôn ngữ | Python 3.11 | Hệ sinh thái LLM và kho vector đều ưu tiên Python |
| LLM | **Gemini 2.5 Flash — gói miễn phí** | ~1.500 lượt/ngày, ~15 lượt/phút, không cần thẻ tín dụng. Dư cho quy mô đồ án |
| LLM dự phòng | Groq free tier · Ollama chạy local | Khi đụng hạn mức hoặc khi cần so sánh mô hình nền |
| Embedding | **Mô hình tiếng Việt chạy local** qua `sentence-transformers` | Xem lập luận bên dưới |
| Kho vector | ChromaDB | `pip install` là chạy, không cần Docker. Có metadata filter — cần để lọc `status = active` ngay ở tầng truy vấn |
| Kiểm thử | pytest + LLM giả lập | Chạy offline, không tốn hạn mức, kết quả lặp lại được; đồng thời là baseline "không-LLM" |

### Vì sao tách embedding ra chạy local

Không phải để tiết kiệm tiền — mà vì **cấu trúc lời gọi**:

- LLM được gọi ~2 lần mỗi lượt hội thoại (trích xuất + sinh phản hồi).
- Embedding được gọi cho **mỗi fact trích được, mỗi truy vấn con, mỗi lần ghép slot**, và
  **mỗi lần quét tham số** ở tuần 6.

Một lần quét ngưỡng τ trên 200 câu test × 10 giá trị ngưỡng là hàng nghìn lời gọi embedding.
Đặt nó lên API nghĩa là đốt hết hạn mức 1.500 lượt/ngày trong một buổi chiều. Chạy local thì
không giới hạn, chạy lại thí nghiệm bao nhiêu lần cũng được.

Lợi ích kèm theo: các mô hình embedding chuyên tiếng Việt (`bkai-foundation-models/vietnamese-bi-encoder`,
`dangvantuan/vietnamese-embedding`) hoặc đa ngữ (`intfloat/multilingual-e5-base`) xử lý dữ
liệu tiếng Việt của nhóm tốt hơn embedding đa ngữ chung. Tuần 6 sẽ so vài mô hình và báo
cáo số, không chọn theo cảm tính.

### Đánh đổi phải nói rõ với mentor

Gói miễn phí của Gemini có điều khoản cho phép dùng dữ liệu để huấn luyện. Vì vậy nhóm chỉ
dùng **dữ liệu tự sinh và dữ liệu benchmark công khai**, không dùng dữ liệu cá nhân thật.
Với đồ án thì ràng buộc này không ảnh hưởng gì.

---

## 4. Lược đồ bộ nhớ

Mỗi ký ức là một **slot**: `(subject, attribute) → value`, kèm số thứ tự đơn điệu `seq`.

| Nhóm trường | Trường | Phục vụ năng lực |
|---|---|---|
| Nhận dạng | `subject` · `attribute` · `value` · `text` | 1 |
| Độ mới | `seq` · `status` · `superseded_by` | 4, 5 |
| Thời gian | `valid_from` · `invalidated_at` · `event_time` | 3, 8 |
| Phân loại | `memory_type` (`semantic` / `preference` / `episodic` / `procedural`) · `pinned` | 7, 8 |
| Rà soát | `needs_review` | 5 |
| Truy vết | `session_id` · `turn_id` · `source_text` | mọi năng lực (debug) |

**Vì sao slot thay vì câu tự do.** Mem0 lưu fact dạng câu, nên để biết hai câu có nói về cùng
một thứ hay không phải đưa cả hai vào lời nhắc cho LLM so sánh. Khóa slot biến việc đó thành
một phép tra khóa. Ký ức `episodic` vẫn lưu dạng câu tự do — slot chỉ áp cho fact có thuộc
tính rõ ràng.

**Bản cũ không bị xóa**, chỉ chuyển `superseded` và giữ khoảng hiệu lực — nhờ đó năng lực 3
(suy luận thời gian) trả lời được câu "hồi tháng 5 trình độ tôi là gì?".

---

## 5. Vòng lặp bốn pha

| Pha | Ai làm | Nội dung |
|---|---|---|
| 1 · Trích xuất | **LLM** | Lượt hội thoại → danh sách fact có cấu trúc, kèm phân loại `memory_type` |
| 2 · Cập nhật | **Python** | Ghép slot → ADD / UPDATE / DELETE / NOOP / CONFLICT. Không gọi LLM |
| 3 · Truy xuất | Embedding + Python | Tách truy vấn con → top-k → lọc bản cũ 2 lớp → nạp ký ức `pinned` → phát tín hiệu từ chối |
| 4 · Sinh phản hồi | **LLM** | Ký ức vào lời nhắc kèm `seq`; ký ức `procedural` vào system prompt |

**Chi tiết dễ bỏ qua:** pha 3 lọc bản cũ **hai lớp** — lọc `status` ở tầng truy vấn, rồi gom
theo slot chỉ giữ `max(seq)`. Cần cả hai vì embedding của "trình độ N5" và "trình độ N4" gần
như trùng nhau, nên top-k rất dễ trả về cả hai; khi lời nhắc chứa hai fact mâu thuẫn thì mô
hình đoán bừa.

**Phân biệt cập nhật và mâu thuẫn.** Cập nhật là giá trị đổi theo thời gian (có thứ tự →
`UPDATE`). Mâu thuẫn là hai giá trị trái nhau xuất hiện cùng lúc (không có thứ tự →
`CONFLICT`, đánh dấu cần rà soát thay vì chọn bừa). BEAM chấm chúng như hai năng lực riêng.

---

## 6. Kế hoạch đánh giá

### Ba trục, áp cho cả tám năng lực

| Trục | Thang đo |
|---|---|
| Độ chính xác | Accuracy **tách theo từng loại câu hỏi** (không gộp một con số chung), chấm bằng LLM-as-a-Judge với mô hình chấm và lời nhắc chấm công bố kèm |
| Tính nhất quán | Tỉ lệ dùng đúng fact sau cập nhật · tỉ lệ tự mâu thuẫn · tỉ lệ từ chối đúng lúc · tỉ lệ tôn trọng ràng buộc đã ghi nhớ |
| Hiệu năng | p50 / p95 tách riêng pha truy xuất và tổng đầu–cuối · token mỗi truy vấn · số bản ghi trong kho |

### Bốn cấu hình đối chứng (nghiên cứu cắt bỏ thành phần)

| Cấu hình | Mô tả | Chứng minh điều gì |
|---|---|---|
| `full-context` | Nhồi toàn bộ lịch sử vào lời nhắc | Baseline trên; chi phí token và điểm tụt khi lịch sử dài |
| `rag-only` | Truy xuất theo embedding, không có cập nhật | Truy xuất đơn thuần giải được năng lực nào |
| `llm-judge` | Có slot, nhưng để LLM tự chọn bản mới | Đối chứng cho cơ chế cập nhật tất định |
| `ours` | Hệ đầy đủ | Cấu hình đề xuất, so trên cả tám năng lực |

Mọi cấu hình cố định **cùng mô hình nền – cùng k – cùng ngân sách token**.

### Dữ liệu

- **LongMemEval-S** — benchmark chính, phủ 5 năng lực.
- **FactConsolidation** (MemoryAgentBench) — năng lực 4 và 5.
- **BEAM** — đối chiếu các năng lực còn lại (chỉ lấy mức 128K, không chạy mức 10M).
- **Bộ test tiếng Việt tự xây** — 150–200 câu, sinh bằng script, phủ cả tám năng lực, chèn
  nhiễu 6K / 32K / 64K token.

---

## 7. Lộ trình 8 tuần (đã điều chỉnh)

| Tuần | Nội dung | Năng lực |
|---|---|---|
| 1 | Nghiên cứu nền tảng, đặt vấn đề, phạm vi | — |
| 2 | Rà soát benchmark, khung 8 năng lực, kiến trúc, chốt công nghệ | — |
| 3 | Pipeline lưu trữ & truy xuất chạy đầu–cuối | 1 |
| 4 | ADD/UPDATE/DELETE/NOOP/CONFLICT | 4, 5 |
| 5 | Tách truy vấn con, khoảng hiệu lực, ký ức pinned; tích hợp agent | 2, 3, 7 |
| 6 | Hiệu chỉnh ngưỡng từ chối, tóm tắt phiên; bộ test tiếng Việt | 6, 8 |
| 7 | Chạy đủ 4 cấu hình × 3 trục; tối ưu hiệu năng; hoàn thiện demo | tất cả |
| 8 | Báo cáo, tài liệu, đóng gói mã nguồn, trình bày cuối | — |

---

## 8. Rủi ro

| Rủi ro | Ảnh hưởng | Xử lý |
|---|---|---|
| LLM đặt tên `attribute` không ổn định | Cùng thuộc tính bị tách 2 slot → mất khả năng phát hiện xung đột | Ghép slot bằng embedding tên thuộc tính (ngưỡng 0.82); dự phòng là từ điển slot cố định; quét ngưỡng 0.70–0.95 ở tuần 6 |
| Tám năng lực quá rộng cho 8 tuần | Không năng lực nào đủ sâu | Mỗi năng lực chỉ cần chạy được + có test. Hạng mục cắt được đầu tiên: năng lực 8 (tóm tắt) và bộ test tiếng Việt |
| Hạn mức Gemini thay đổi | Gián đoạn thí nghiệm | Adapter cho phép đổi sang Groq hoặc Ollama local trong một file |
| Embedding tiếng Việt yếu | Truy xuất trượt, kéo tụt mọi năng lực | So 3 mô hình ở tuần 6 và báo cáo số |
| Thang đo chấm bằng LLM không ổn định | Kết quả không tin được | Công bố mô hình chấm và lời nhắc chấm; chấm lại một mẫu bằng tay để đối chiếu |

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
