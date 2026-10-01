# Kết quả LongMemEval-S

## 1. Độ chính xác (%, số câu trong ngoặc)

| Nhóm | full\dev |
|---|---|
| single-session-user | 95.2 (21) |
| single-session-assistant | 82.4 (17) |
| single-session-preference | 77.8 (9) |
| multi-session | 80.0 (40) |
| temporal-reasoning | 85.0 (40) |
| knowledge-update | 87.0 (23) |
| **_abs (biết từ chối)** | 75.0 (4) |
| không _abs | 84.9 (146) |
| **Tổng (micro)** | 84.7 (150) |
| **Macro (TB 6 loại)** | 84.6 |

### Theo 5 năng lực (IE = 3 loại single-session; ABS tách riêng)

| Năng lực | full\dev |
|---|---|
| IE | 87.2 (47) |
| MR | 82.1 (39) |
| TR | 84.2 (38) |
| KU | 86.4 (22) |
| ABS | 75.0 (4) |

## 2. Truy xuất (%)

| Chỉ số | full\dev |
|---|---|
| Recall bộ lọc phiên (TB) | 98.5 |
| Recall phiên do công cụ chạm tới (TB) | 99.6 |
| Câu có ≥1 fact từ phiên bằng chứng | 100.0 |
| Câu có ≥1 fact từ đúng LƯỢT chứa đáp án | 98.0 |

## 3. Chi phí

| Chỉ số (mỗi câu) | full\dev |
|---|---|
| Số lần gọi công cụ TB | 3.5 |
| Lời gọi LLM trả lời TB | 3.7 |
| Lời gọi LLM dựng (thật, không cache) TB | 22.4 |
| Token dựng TB | 89172 |
| Token trả lời TB | 12036 |
| Tỉ trọng token dựng / tổng | 88.1 |
| Độ trễ trả lời p50 / p95 (s) | 33.2 / 65.1 |
| Độ trễ dựng p50 / p95 (s) | 423.9 / 1384.2 |
| Câu bị ép trả lời (hết lượt) | 0 |

_Token dựng chỉ tính lần dựng đầu (lượt sau dùng lại đồ thị/cache)._

## 4. Phân loại câu sai (tự động; 'nhầm thực thể' cần soi tay)

| Loại lỗi | full\dev |
|---|---|
| filtered_out | 1 |
| not_extracted | 0 |
| tool_miss | 0 |
| sql_error | 0 |
| reasoning | 21 |
| abstention_fail | 1 |
| llm_error | 0 |

## 5. Mô hình thực sự phục vụ (response.model)

- **full\dev**: {'gpt-5.6-luna': 3998, 'gpt-5.6-terra': 150}
