# %% [markdown]
# # Nhúng sẵn LongMemEval-S bằng BGE-M3 trên GPU Kaggle
#
# Đây là PHẦN DUY NHẤT của hệ cần GPU. Kết quả là file `embed_cache.db` đúng định dạng cache
# của `ltm/adapters/embed.py` (bảng `emb(model, h=sha1(text), dim, vec float16)`).
# Tải file về, đặt vào `apexmem/data/cache/embed_cache.db` → hệ chạy local không phải nhúng lại
# ~250K lượt hội thoại trên CPU (mất nhiều giờ).
#
# Cách chạy trên Kaggle:
#   1. New Notebook → Settings: Accelerator = GPU T4 (x1 là đủ), Internet = ON
#   2. Dán toàn bộ file này vào một cell (hoặc tách theo các dấu `# %%`) → Run All
#   3. Xong (~20–30 phút) → tab Output → tải `embed_cache.db` (~0,5 GB)
#
# BẮT BUỘC khớp với config.yaml ở máy local:
#   embed.model = BAAI/bge-m3      embed.max_seq_length = 512
#   eval.dataset_path trỏ tới CÙNG file longmemeval_s_cleaned.json
# Lệch bất kỳ điều nào → khóa cache khác → hệ âm thầm nhúng lại trên CPU.

# %%
import subprocess, sys
subprocess.run([sys.executable, "-m", "pip", "install", "-q", "sentence-transformers",
                "huggingface_hub"], check=False)

# %%
import hashlib, json, os, sqlite3, time
import numpy as np
import torch
from huggingface_hub import hf_hub_download
from sentence_transformers import SentenceTransformer

MODEL = "BAAI/bge-m3"
MAX_SEQ = 512
BATCH = 128
OUT = "/kaggle/working/embed_cache.db"

# Nếu đã thêm dataset LongMemEval vào notebook (Add Input), đổi DATA thành đường dẫn đó.
DATA = hf_hub_download("xiaowu0162/longmemeval-cleaned", "longmemeval_s_cleaned.json",
                       repo_type="dataset")
print("GPU:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "KHÔNG CÓ GPU!")

# %% gom mọi văn bản cần nhúng: nội dung từng lượt + câu hỏi (đúng như hệ local dùng)
data = json.load(open(DATA, encoding="utf-8"))
texts = {}
for e in data:
    texts[hashlib.sha1(e["question"].encode("utf-8")).hexdigest()] = e["question"]
    for sess in e["haystack_sessions"]:
        for t in sess:
            c = t.get("content") if isinstance(t, dict) else None
            if c:
                texts[hashlib.sha1(c.encode("utf-8")).hexdigest()] = c
print(f"{len(data)} câu hỏi · {len(texts):,} văn bản khác nhau")

# %% bỏ qua phần đã có (chạy lại được nếu notebook bị ngắt giữa chừng)
con = sqlite3.connect(OUT)
con.execute("CREATE TABLE IF NOT EXISTS emb (model TEXT NOT NULL, h TEXT NOT NULL, "
            "dim INTEGER NOT NULL, vec BLOB NOT NULL, PRIMARY KEY (model, h))")
have = {h for (h,) in con.execute("SELECT h FROM emb WHERE model=?", (MODEL,))}
todo = [(h, t) for h, t in texts.items() if h not in have]
todo.sort(key=lambda x: len(x[1]))           # gom câu cùng độ dài → ít padding, nhanh hơn
print(f"còn {len(todo):,} cần nhúng")

# %%
model = SentenceTransformer(MODEL, device="cuda")
model.max_seq_length = MAX_SEQ
model.half()                                   # fp16 trên GPU: nhanh gấp ~2, sai số không đáng kể

t0 = time.time()
CHUNK = 20_000
for i in range(0, len(todo), CHUNK):
    part = todo[i:i + CHUNK]
    vecs = model.encode([t for _, t in part], batch_size=BATCH, normalize_embeddings=True,
                        convert_to_numpy=True, show_progress_bar=True)
    con.executemany("INSERT OR REPLACE INTO emb(model, h, dim, vec) VALUES (?,?,?,?)",
                    [(MODEL, h, int(v.shape[0]), v.astype(np.float16).tobytes())
                     for (h, _), v in zip(part, vecs)])
    con.commit()
    print(f"{i + len(part):,}/{len(todo):,} · {time.time() - t0:.0f}s")

# %% kiểm tra nhanh
n = con.execute("SELECT COUNT(*) FROM emb WHERE model=?", (MODEL,)).fetchone()[0]
con.execute("VACUUM")
con.close()
print(f"XONG: {n:,} vector · {os.path.getsize(OUT) / 1e9:.2f} GB → tải {OUT} ở tab Output")
