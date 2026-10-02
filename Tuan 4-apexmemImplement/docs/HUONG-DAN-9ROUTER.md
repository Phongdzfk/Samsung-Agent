# Hướng dẫn dùng 9router cho dự án (nhiều tài khoản, tự xoay khi hết hạn mức)

9router là một **proxy chạy trên máy anh** (`http://localhost:20128`). Code Python gọi nó như
gọi API OpenAI; 9router chuyển tiếp tới tài khoản ChatGPT/Codex anh đã đăng nhập.

```
ltm (Python) ──OpenAI API──► 9router :20128 ──► Codex tài khoản #1
                                          ├──► Codex tài khoản #2   (xoay vòng / dự phòng)
                                          └──► Codex tài khoản #3
```

---

## 1. Cài và chạy

Cần **Node.js 20+** (tải bản LTS ở nodejs.org).

```powershell
npm install -g 9router
9router
```

Dashboard tự mở ở `http://localhost:20128`. Mật khẩu đăng nhập lần đầu là **`123456`** — vào
Settings đổi ngay.

Mỗi lần chạy thí nghiệm phải để cửa sổ `9router` mở (tắt là code Python báo lỗi kết nối).

## 2. Thêm nhiều tài khoản Codex

1. Dashboard → **Providers** → **Codex** → **Connect** → đăng nhập tài khoản ChatGPT thứ nhất
   (OAuth mở trình duyệt, dùng cổng 1455).
2. Trong trang Codex bấm **Add Account** → đăng nhập tài khoản thứ hai. Lặp lại cho tài khoản thứ ba…
   Mẹo: dùng cửa sổ ẩn danh hoặc đăng xuất chatgpt.com trước, để trình duyệt không tự đăng nhập
   lại tài khoản cũ.
3. Mỗi tài khoản hiện một dòng riêng, kèm hạn mức còn lại (Codex có hạn mức theo **cửa sổ 5 giờ** và
   **theo tuần**).

### 9router xoay tài khoản thế nào

Khi code gọi model `cx/gpt-5.5`:

1. 9router chọn một tài khoản Codex (xoay vòng hoặc theo độ ưu tiên — chỉnh trong Settings).
2. Nếu tài khoản đó trả lỗi hết hạn mức / 429, 9router **đánh dấu tài khoản đang nghỉ**
   (`rateLimitedUntil`) và **thử lại ngay bằng tài khoản Codex kế tiếp** — vẫn là `gpt-5.5`.
3. Hết sạch tài khoản Codex → 9router trả lỗi về cho code.
   Code của nhóm (`ltm/adapters/llm.py`) sẽ **tự chờ** (5 s, 10 s, 20 s… tối đa 10 phút/lần,
   8 lần) rồi thử lại. Bị ngắt hẳn thì chạy lại đúng lệnh cũ: câu đã xong được bỏ qua, lời gọi
   đã có trong cache không tốn hạn mức.

## 3. Điều QUAN TRỌNG NHẤT cho số liệu: gọi thẳng model, KHÔNG dùng combo

9router có hai cơ chế dự phòng khác nhau:

| Cơ chế | Khi hết hạn mức thì | Dùng cho đánh giá? |
|---|---|---|
| **Nhiều tài khoản cùng provider** (gọi `cx/gpt-5.5`) | chuyển sang tài khoản khác, **cùng mô hình** | ✅ Dùng — số liệu vẫn hợp lệ |
| **Combo** (gọi tên combo, vd. `my-stack`) | chuyển sang **mô hình khác** (GLM, Kiro…) | ❌ Không — một phần câu hỏi bị mô hình khác trả lời mà không ai biết |

Vì vậy `config.yaml` để `model: cx/gpt-5.5` (tên model trực tiếp). Ngoài ra code còn ghi
`response.model` của **mọi** lời gọi; bảng báo cáo có mục "Mô hình thực sự phục vụ" và cảnh báo nếu
có lời gọi nào bị phục vụ bởi mô hình khác. Muốn dừng ngay khi điều đó xảy ra: `strict_model: true`.

Combo thì vẫn tiện cho **demo chat** (không cần số liệu chính xác) — có thể đặt
`LTM__LLM__MODEL=<tên-combo>` khi chạy `python -m ltm.demo.chat`.

## 4. Nối code với 9router

1. Dashboard → **Endpoint / API Keys** → tạo key → copy.
2. Trong thư mục `apexmem`: chép `.env.example` thành `.env`, điền:
   ```
   NINEROUTER_API_KEY=sk-...
   ```
3. Kiểm tra:
   ```powershell
   python -m ltm.check
   ```
   Lệnh này liệt kê model 9router đang có, gọi thử từng vai trò, in **model thực sự phục vụ**, và
   kiểm tra function calling có đi qua được không.

| `ltm.check` báo | Nghĩa là | Sửa |
|---|---|---|
| không kết nối được | 9router chưa chạy | mở terminal chạy `9router` |
| `auth` / 401 | sai key | tạo lại key, sửa `.env` |
| `?` cạnh tên model | tên model sai | xem danh sách trong dashboard, sửa `llm.model` / `llm.roles` |
| model không gọi công cụ | provider không chuyển tiếp tool calling | `agent.protocol: json` trong `config.yaml` |
| lỗi liên quan stream | provider chỉ trả stream | `llm.stream: true` |
| `⚠ KHÁC MODEL` | router đổi model | kiểm tra không dùng combo; tài khoản có quyền dùng model đó |

## 5. Mô hình cho từng vai trò

```yaml
llm:
  model: cx/gpt-5.5          # trích xuất, giải quyết thực thể, agent trả lời
  roles:
    judge: cx/gpt-5.4        # mô hình chấm — nên KHÁC mô hình trả lời
```

Script chấm gốc của LongMemEval dùng GPT-4o. Nếu tài khoản có model đó trong 9router thì đặt
`judge` sang nó để sát bài gốc; nếu không, ghi rõ mô hình chấm trong báo cáo.

## 6. Ước lượng số lời gọi — để biết cần bao nhiêu tài khoản

Mỗi câu hỏi LongMemEval-S (giữ 10/~50 phiên):

| Pha | Lời gọi | Ghi chú |
|---|---|---|
| Dựng đồ thị | ~10–25 | 1 lời gọi trích xuất / 12 lượt + 0–1 lời gọi giải quyết / đoạn. **Chỉ lần đầu**; các cấu hình sau (a1, a2, steps*) dùng lại đồ thị; baseline simple_search_kv không cần đồ thị |
| Trả lời (agent) | ~4–15 | tối đa 20 bước |
| Chấm | 1 × số lần chấm | |

→ 20 câu ≈ 500–800 lời gọi; 150 câu dev ≈ 4.000–6.000 lời gọi cho lần chạy `full` đầu tiên.
**Luôn chạy `--n 20` trước**, xem mục "Chi phí" trong báo cáo, rồi mới quyết định chạy cả tập.

Gợi ý tốc độ: `eval.workers: 2` (mỗi tài khoản chịu ~1 luồng). Tăng luồng không làm nhanh hơn nếu
chỉ có 1–2 tài khoản — chỉ sinh thêm lỗi 429.

## 7. Lưu ý trước khi dùng nhiều tài khoản

- Điều khoản sử dụng của OpenAI **cấm lách giới hạn sử dụng** (rate limit / usage limit). Gộp nhiều
  tài khoản để vượt hạn mức có rủi ro bị khóa tài khoản. Cách an toàn: mỗi thành viên dùng tài khoản
  của chính mình (nhóm 2 người → 2 tài khoản), không mua/mượn tài khoản.
- Dữ liệu gửi đi là LongMemEval (công khai) nên không có vấn đề riêng tư. Với demo chat, đừng nhập
  thông tin cá nhân thật.
- Theo dõi hạn mức ở Dashboard → **Usage** (số "cost" ở đó chỉ là ước tính để so sánh, không phải
  hóa đơn).
