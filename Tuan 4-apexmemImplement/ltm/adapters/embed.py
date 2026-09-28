"""Embedding có cache.

Cache là SQLite `emb(model, h, dim, vec)` với h = sha1(text), vec = float16. Script Kaggle
(kaggle/embed_longmemeval.py) ghi ĐÚNG định dạng này → tải file về là hệ thống dùng lại,
không phải nhúng lại 247K lượt trên CPU.
"""
from __future__ import annotations

import re
import sqlite3
import threading
from pathlib import Path
from typing import Sequence

import numpy as np

from ..util import sha1

CACHE_SCHEMA = ("CREATE TABLE IF NOT EXISTS emb (model TEXT NOT NULL, h TEXT NOT NULL, "
                "dim INTEGER NOT NULL, vec BLOB NOT NULL, PRIMARY KEY (model, h))")


class EmbedCache:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute(CACHE_SCHEMA)
        self._lock = threading.Lock()

    def get_many(self, model: str, hashes: Sequence[str]) -> dict[str, np.ndarray]:
        out: dict[str, np.ndarray] = {}
        uniq = list(dict.fromkeys(hashes))
        with self._lock:
            for i in range(0, len(uniq), 900):
                part = uniq[i:i + 900]
                ph = ",".join("?" * len(part))
                for h, dim, blob in self.conn.execute(
                        f"SELECT h, dim, vec FROM emb WHERE model=? AND h IN ({ph})", [model, *part]):
                    out[h] = np.frombuffer(blob, dtype=np.float16).astype(np.float32)
        return out

    def put_many(self, model: str, items: dict[str, np.ndarray]) -> None:
        with self._lock, self.conn:
            self.conn.executemany(
                "INSERT OR REPLACE INTO emb(model, h, dim, vec) VALUES (?,?,?,?)",
                [(model, h, int(v.shape[0]), v.astype(np.float16).tobytes()) for h, v in items.items()])

    def count(self, model: str) -> int:
        with self._lock:
            return self.conn.execute("SELECT COUNT(*) FROM emb WHERE model=?", (model,)).fetchone()[0]


class Embedder:
    """Giao diện: encode(texts) -> ma trận (n, dim) đã chuẩn hóa L2, float32."""

    model_name: str = "base"
    dim: int = 0

    def __init__(self, cache: EmbedCache | None = None):
        self.cache = cache
        self.stats = {"hit": 0, "miss": 0}
        self._lock = threading.Lock()

    def _encode(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        texts = list(texts)
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        hashes = [sha1(t) for t in texts]
        found = self.cache.get_many(self.model_name, hashes) if self.cache else {}
        missing = list(dict.fromkeys(h for h in hashes if h not in found))
        self.stats["hit"] += sum(1 for h in hashes if h in found)
        if missing:
            by_hash = {h: t for h, t in zip(hashes, texts)}
            with self._lock:                               # mô hình không an toàn đa luồng
                vecs = self._encode([by_hash[h] for h in missing])
            new = {h: _l2(v) for h, v in zip(missing, vecs)}
            if self.cache:
                self.cache.put_many(self.model_name, new)
            found.update(new)
            self.stats["miss"] += len(missing)
        out = np.stack([found[h] for h in hashes]).astype(np.float32)
        return _l2_rows(out)


def _l2(v: np.ndarray) -> np.ndarray:
    n = float(np.linalg.norm(v))
    return v / n if n > 0 else v


def _l2_rows(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=1, keepdims=True)
    n[n == 0] = 1
    return m / n


class STEmbedder(Embedder):
    """sentence-transformers (BGE-M3 mặc định). Nạp mô hình lười: chỉ khi thật sự cần nhúng."""

    def __init__(self, model_name: str, device: str = "cpu", batch_size: int = 16,
                 max_seq_length: int = 512, cache: EmbedCache | None = None):
        super().__init__(cache)
        self.model_name, self.device = model_name, device
        self.batch_size, self.max_seq_length = batch_size, max_seq_length
        self._model = None
        self.dim = 1024 if "bge-m3" in model_name.lower() else 0

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            print(f"[embed] nạp {self.model_name} trên {self.device} ...", flush=True)
            self._model = SentenceTransformer(self.model_name, device=self.device)
            self._model.max_seq_length = self.max_seq_length
            self.dim = self._model.get_sentence_embedding_dimension()
        return self._model

    def _encode(self, texts):
        m = self._load()
        return m.encode(texts, batch_size=self.batch_size, normalize_embeddings=True,
                        convert_to_numpy=True, show_progress_bar=len(texts) > 256)


class HashEmbedder(Embedder):
    """Embedding băm từ (bag-of-words + bigram ký tự). Chỉ để test offline, KHÔNG dùng đánh giá."""

    model_name = "hash-256"

    def __init__(self, dim: int = 256, cache: EmbedCache | None = None):
        super().__init__(cache)
        self.dim = dim

    def _encode(self, texts):
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, t in enumerate(texts):
            words = re.findall(r"[a-z0-9]+", t.lower())
            feats = words + [w[j:j + 3] for w in words for j in range(max(1, len(w) - 2))]
            for f in feats:
                h = int(sha1(f)[:8], 16)
                out[i, h % self.dim] += 1.0 if (h >> 8) & 1 else -1.0
        return out


def build_embedder(cfg_embed: dict) -> Embedder:
    from ..config import resolve_path

    cache = EmbedCache(resolve_path(cfg_embed["cache_path"])) if cfg_embed.get("cache_path") else None
    if cfg_embed.get("backend") == "hash":
        return HashEmbedder(cache=cache)
    return STEmbedder(cfg_embed["model"], cfg_embed.get("device", "cpu"),
                      cfg_embed.get("batch_size", 16), cfg_embed.get("max_seq_length", 512), cache)
