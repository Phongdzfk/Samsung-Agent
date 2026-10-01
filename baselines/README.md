# Baseline LightMem trên LongMemEval-S

Đường cơ sở để so sánh với hệ thống APEX-MEM của nhóm. Thư mục này **không sửa** mã nguồn
gốc của LightMem; toàn bộ phần chạy nằm trong một script bọc ngoài.

## Cấu trúc

| Đường dẫn | Là gì | Trong git? |
|---|---|---|
| `run_lightmem.py` | Script chạy LightMem trên LongMemEval-S | có |
| `data/split.json` | Chia dev 150 / test 350, seed 42, phân tầng theo loại | có |
| `results/dev150/cases/*.json` | Kết quả từng câu (câu trả lời, phán quyết chấm, thời gian) | có |
| `results/apexmem-full-dev/` | Kết quả APEX-MEM (full) trên 150 câu dev: `results.jsonl`, `hypotheses.jsonl`, `run_meta.json`, `report.md` | có |
| `report/gen_stats.py` | Gộp kết quả LightMem thành `stats.json` | có |
| `report/compare_apex.py` | So sánh APEX-MEM với LightMem (cặp câu, McNemar, theo loại) thành `compare.json` | có |
| `report/build_deck.js` | Dựng slide từ `stats.json` | có |
| `bao-cao-lightmem-baseline.pptx` | Slide báo cáo | có |
| `ket-qua-baseline-lightmem.md` | Kết quả và phân tích bằng văn bản | có |
| `kich-ban-thuyet-trinh-lightmem.md` | Kịch bản nói cho 11 slide, kèm phần chuẩn bị hỏi đáp | có |
| `report/manual_review.json` | Bản soi tay kiểm tra model chấm (không sinh tự động) | có |
| `LightMem/` | Repo gốc `zjunlp/LightMem` (có git riêng) | không |
| `models/` | LLMLingua-2 + all-MiniLM-L6-v2 (~1,6 GB) | không |
| `data/longmemeval_s.json` | Bộ dữ liệu (277 MB) | không |

## Dựng lại môi trường

```powershell
git clone https://github.com/zjunlp/LightMem.git baselines/LightMem
cd baselines/LightMem
py -m uv venv --python 3.11 .venv          # LightMem yêu cầu Python 3.10–3.11
.venv\Scripts\python.exe -m pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/cu126
.venv\Scripts\python.exe -m pip install -e .
```

Tải hai model vào `baselines/models/`:
`microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank` và
`sentence-transformers/all-MiniLM-L6-v2`.

Tải `longmemeval_s.json` từ `xiaowu0162/longmemeval-cleaned` vào `baselines/data/`.

## Chạy

Cần một endpoint tương thích OpenAI. Nhóm dùng 9router (`npm install -g 9router`,
chạy `9router`, dashboard ở `http://localhost:20128`).

```powershell
cd C:\Samsung-Agent\baselines
$env:NINEROUTER_BASE_URL = "http://127.0.0.1:20128/v1"
$env:NINEROUTER_API_KEY  = "<key lấy từ dashboard 9router>"
$env:LLM_MODEL           = "cx/gpt-5.6-luna"
$env:JUDGE_MODEL         = "cx/gpt-5.6-terra"
$env:PYTHONIOENCODING    = "utf-8"
.\LightMem\.venv\Scripts\python.exe run_lightmem.py --workers 5 --out results\dev150 2>&1 | Tee-Object -FilePath dev150.log
```

Mặc định chỉ chạy tập **dev**; tập test khóa đến tuần 7.

Hai tuỳ chọn để làm thí nghiệm tách phần thiệt do cấu hình:

```powershell
# chỉ chạy một loại câu hỏi
.\LightMem\.venv\Scripts\python.exe run_lightmem.py --qtype single-session-assistant --out resultsssistant-user-only

# lưu cả lượt trợ lý vào bộ nhớ (khác cấu hình gốc của bài báo)
.\LightMem\.venv\Scripts\python.exe run_lightmem.py --qtype single-session-assistant --messages-use user_assistant --out resultsssistant-user-assistant
```

Kết quả hai lượt phải để ở hai thư mục `--out` khác nhau, vì cùng question_id nhưng khác cấu hình.

- Có **resume**: câu nào đã có file trong `results/dev150/cases/` thì bỏ qua, nên chạy lại
  đúng lệnh trên là tiếp tục từ chỗ dừng.
- `--workers` là số câu chạy song song. Trên máy 16 GB, 5 luồng là an toàn; 8–9 luồng nhanh
  hơn nhưng có lúc cạn RAM (`paging file is too small`).
- Đếm tiến độ: `(Get-ChildItem results\dev150\cases).Count`

## Dựng lại slide

```powershell
cd report
python gen_stats.py       # kết quả LightMem -> stats.json (mất 1-2 phút vì phải đọc cả bộ dữ liệu)
python compare_apex.py    # LightMem vs APEX-MEM -> compare.json
node build_deck.js        # stats.json + compare.json + manual_review.json -> ../bao-cao-lightmem-baseline.pptx
```

Mọi số trên slide đọc từ `stats.json`, nên chạy thêm câu xong chỉ cần chạy lại hai lệnh này.
Lần đầu cần `npm install pptxgenjs` trong `report/`.

Xem trước bằng ảnh (cần LibreOffice và `pip install pymupdf`):

```powershell
& "C:\Program Files\LibreOffice\program\soffice.exe" --headless --convert-to pdf --outdir . ..\bao-cao-lightmem-baseline.pptx
python -c "import pymupdf; d=pymupdf.open('bao-cao-lightmem-baseline.pdf'); [p.get_pixmap(dpi=140).save(f'slide-{i:02d}.png') for i,p in enumerate(d,1)]"
```

## Ghi chú về cấu hình

Cấu hình lấy nguyên từ `experiments/longmemeval/run_lightmem_gpt.py` của LightMem, trong đó
`messages_use = "user_only"`: **chỉ lượt của người dùng được đưa vào bộ nhớ**. Đây là lý do
loại câu hỏi `single-session-assistant` đạt điểm rất thấp — hệ không có dữ liệu về những gì
trợ lý đã nói. Muốn đo lại phần này thì đổi sang `user_assistant`, nhưng khi đó không còn
so được với số liệu trong bài báo gốc.

Script tự đổi tham số API cho dòng model GPT-5.x (bỏ `temperature`/`top_p`, đổi
`max_tokens` → `max_completion_tokens`), vì các model này không nhận tham số cũ.

Prompt chấm và hàm đọc phán quyết lấy **nguyên văn** từ script gốc của LightMem, để điểm số
so được với bài báo.
