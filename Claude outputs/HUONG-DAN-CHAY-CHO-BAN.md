# Hướng dẫn chạy đánh giá APEX-MEM trên máy của bạn

Mục tiêu: chạy **nửa B** của 150 câu dev LongMemEval-S trên máy bạn, song song với máy Phong (nửa A),
rồi gửi kết quả về để gộp. Làm đúng thứ tự dưới đây là chạy được, không cần hiểu code.

> Quy tắc vàng: **không sửa `config.yaml`** (trừ `embed.device`). Chỉ cần lệch một tham số là đồ thị
> của hai máy khác nhau, số liệu không gộp được.

---

## 0. Cần chuẩn bị

| Thứ | Ghi chú |
|---|---|
| Windows + **Python 3.10 trở lên** | `python --version` để kiểm tra |
| **Node.js 20+** (bản LTS) | để chạy 9router |
| Git | để lấy code |
| Tài khoản ChatGPT **của chính bạn** | dùng Codex qua 9router |
| ~3 GB ổ trống | cache embedding ~0,8 GB + dữ liệu ~0,3 GB + đồ thị |

Phong gửi cho bạn (qua USB / Drive):

- `embed_cache.db` (~0,8 GB) — embedding BGE-M3 đã nhúng sẵn trên GPU
- `longmemeval_s_cleaned.json` (~265 MB) — hoặc tự tải ở bước 3
- `dev.txt` — danh sách 150 câu dev
- `dev_B.txt` — **các câu bạn phụ trách**
- `config.yaml` — cấu hình chuẩn của nhóm

---

## 1. Lấy code và cài thư viện

```powershell
git clone <link repo Samsung-Agent>        # hoặc: git pull nếu đã có
cd Samsung-Agent\"Tuan 4-apexmemImplement"

python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m pytest                           # phải ra "113 passed" (chạy offline, ~5 giây)
```

Nếu PowerShell chặn `activate`: chạy một lần
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` rồi thử lại.

---

## 2. Đặt dữ liệu vào đúng chỗ

Trong thư mục `Tuan 4-apexmemImplement`:

```
data\
  cache\embed_cache.db                         ← file Phong gửi
  longmemeval\longmemeval_s_cleaned.json       ← file Phong gửi (hoặc bước 3)
  splits\dev.txt                               ← file Phong gửi
config.yaml                                    ← GHI ĐÈ bằng file Phong gửi
dev_B.txt                                      ← để ngay thư mục này
```

```powershell
mkdir data\cache, data\longmemeval, data\splits
```

⚠ **Không** đặt thư mục dự án trong OneDrive / Google Drive đang đồng bộ: file SQLite bị đồng bộ lúc
đang ghi rất dễ hỏng.

Được phép sửa đúng 1 dòng trong `config.yaml`: `embed.device` — để `cpu`, hoặc `cuda` nếu máy có GPU
**và** `python -c "import torch; print(torch.cuda.is_available())"` in ra `True`. Dòng này không ảnh
hưởng số liệu.

---

## 3. (Chỉ khi chưa có file dữ liệu) Tải LongMemEval-S

```powershell
python -m ltm.eval.download
```

---

## 4. Cài và cấu hình 9router

```powershell
npm install -g 9router
9router
```

1. Dashboard tự mở ở `http://localhost:20128`, mật khẩu đầu tiên là `123456` → vào Settings đổi ngay.
2. **Providers → Codex → Connect** → đăng nhập tài khoản ChatGPT của bạn (có thể **Add Account** thêm
   tài khoản khác của chính bạn).
3. **Endpoint / API Keys** → tạo key → copy.
4. Trong thư mục dự án, tạo file `.env` (chép từ `.env.example`) với một dòng:
   ```
   NINEROUTER_API_KEY=sk-...
   ```
5. **Để cửa sổ `9router` luôn mở** trong lúc chạy.

Lưu ý tài khoản:
- Đang dùng 9router thì **đừng đăng nhập cùng tài khoản đó ở Codex CLI / VS Code / app Codex** — dễ bị
  thu hồi token (lỗi `401 token_revoked`).
- Không gộp nhiều tài khoản mượn/mua để lách hạn mức — vi phạm điều khoản OpenAI, dễ bị khóa.

---

## 5. Kiểm tra trước khi chạy

```powershell
python -m ltm.check
```

Phải thấy đủ các dòng ✓:

- kết nối 9router được;
- `cx/gpt-5.6-luna` (trả lời, trích xuất) và `cx/gpt-5.6-terra` (chấm điểm) đều gọi được, và dòng
  "phục vụ bởi" ra đúng tên model đó;
- function calling đi qua được;
- cache embedding có **hơn 100.000 vector**.

Dòng nào ✗ → xem mục 8.

---

## 6. Chạy

### 6.1. Hệ đầy đủ (lâu nhất)

```powershell
python -m ltm.eval.run --config full --ids-file dev_B.txt --run-name dev-v2 --workers 1
```

- Dòng đầu tiên in ra có dạng `đồ thị: ...\data\graphs\<mã 10 ký tự>`.
  **Gửi ngay mã này cho Phong** để so với máy Phong — hai mã phải **giống hệt**. Khác mã = cấu hình
  lệch → dừng lại (Ctrl+C) và kiểm tra `config.yaml`.
- Mỗi câu in một dòng `ĐÚNG`/`SAI`. Ước tính vài phút một câu (đo thực tế sau 3–5 câu đầu).
- **Bị ngắt** (tắt máy, hết hạn mức, lỗi mạng) → chạy lại **đúng lệnh cũ**: câu đã xong được bỏ qua,
  lời gọi LLM đã làm nằm trong cache, không tốn lại hạn mức.
- Nếu hiện `[run] DỪNG: lỗi cấu hình LLM` hoặc `hết … lượt thử lại, có thể đã hết hạn mức`: tài khoản
  hết hạn mức hoặc bị lỗi → chờ hạn mức hồi (cửa sổ 5 giờ) hoặc xử lý theo mục 8, rồi chạy lại lệnh cũ.

### 6.2. Hai baseline (nhanh, chạy sau khi 6.1 xong)

```powershell
python -m ltm.eval.run --config simple_search    --ids-file dev_B.txt --run-name dev-v2 --workers 1
python -m ltm.eval.run --config simple_search_kv --ids-file dev_B.txt --run-name dev-v2 --workers 1
```

`simple_search` dùng lại đồ thị của 6.1 (1 lời gọi trả lời/câu). `simple_search_kv` không cần đồ thị.

### 6.3. Xem nhanh kết quả của bạn

```powershell
python -m ltm.eval.report data\runs\full\dev-v2 data\runs\simple_search\dev-v2 data\runs\simple_search_kv\dev-v2
```

---

## 7. Gửi kết quả về cho Phong

Nén và gửi các thư mục/file sau:

| Gửi | Để làm gì |
|---|---|
| `data\runs\` (cả thư mục) | kết quả từng câu — bắt buộc |
| `data\graphs\<mã>\` | đồ thị từng câu — để Phong chạy thêm cấu hình/soi lỗi mà không dựng lại |
| `data\cache\llm_cache.db` | cache lời gọi LLM — để gộp, tránh gọi lại |

Không gửi `.env` (chứa key của bạn).

---

## 8. Lỗi thường gặp

| Thấy gì | Nguyên nhân | Làm gì |
|---|---|---|
| `ltm.check`: không kết nối được | 9router chưa chạy | mở terminal chạy `9router` |
| `401` / `auth` | sai key trong `.env` | tạo lại key ở dashboard |
| `401 token_revoked` trên 9router | tài khoản bị thu hồi đăng nhập | xóa tài khoản trong Codex → Add Account đăng nhập lại; đóng Codex CLI/app đang dùng cùng tài khoản. Bị lại ngay → thôi dùng tài khoản đó |
| `404 model_not_found` | tài khoản không có quyền dùng model / sai tên | kiểm tra tên model trong dashboard 9router; báo Phong |
| `⚠ KHÁC MODEL` trong `ltm.check` hoặc báo cáo | router trả lời bằng model khác | đảm bảo không dùng combo; báo Phong |
| `Torch not compiled with CUDA enabled` | torch bản CPU | đặt `embed.device: cpu` |
| Chạy rất chậm ở bước lọc, `ltm.check` báo cache ít vector | cache embedding không khớp | kiểm tra `data\cache\embed_cache.db` đúng chỗ; `config.yaml` là bản của Phong (model `BAAI/bge-m3`, `max_seq_length: 512`) |
| Mã đồ thị khác máy Phong | `config.yaml` lệch | chép lại đúng `config.yaml` của Phong (chỉ được đổi `embed.device`) |
| `database is locked` | đang mở file `.db` bằng phần mềm khác lúc chạy | đóng DB Browser rồi chạy lại lệnh cũ |
