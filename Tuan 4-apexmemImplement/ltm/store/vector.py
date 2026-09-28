"""Chỉ mục vector — DẪN XUẤT hoàn toàn từ đồ thị SQLite.

Không lưu vector trong file đồ thị: ma trận được dựng lúc cần từ (id, văn bản) trong SQLite,
vector lấy qua Embedder (có cache theo sha1(text) + tên mô hình). Hệ quả:
  - xóa chỉ mục = không mất gì; đổi mô hình embedding = cache trượt, tự nhúng lại;
  - lượt hội thoại đã nhúng sẵn trên Kaggle được dùng lại ngay (cùng khóa sha1(text)).
Với vài nghìn mục mỗi câu hỏi, tìm kiếm vét cạn bằng numpy nhanh hơn dựng ANN.
"""
from __future__ import annotations

import json
import threading
from typing import Iterable, Sequence

import numpy as np

from ..adapters.embed import Embedder
from .graphdb import GraphDB

KINDS = ("entity", "property", "fact", "turn")


def entity_text(name: str, type_: str, aliases: Iterable[str]) -> str:
    al = [a for a in aliases if a and a != name]
    return f"{name} ({type_})" + (f"; also known as {', '.join(al)}" if al else "")


def property_text(name: str) -> str:
    return name.replace("_", " ")


class VectorIndex:
    def __init__(self, db: GraphDB, embedder: Embedder):
        self.db, self.embedder = db, embedder
        self._ids: dict[str, list[int]] = {}
        self._pos: dict[str, dict[int, int]] = {}
        self._mat: dict[str, np.ndarray] = {}
        self._lock = threading.Lock()

    # ---- nguồn văn bản cho từng loại, đọc thẳng từ sổ cái
    def _source(self, kind: str) -> list[tuple[int, str]]:
        c = self.db.conn
        if kind == "entity":
            return [(r["entity_id"], entity_text(r["name"], r["type"], json.loads(r["aliases_json"])))
                    for r in c.execute("SELECT entity_id, name, type, aliases_json FROM entities")]
        if kind == "property":
            return [(r["property_id"], property_text(r["name"]))
                    for r in c.execute("SELECT property_id, name FROM properties")]
        if kind == "fact":
            return [(r["rowid"], r["content"]) for r in c.execute("SELECT rowid, content FROM facts_fts")]
        if kind == "turn":
            return [(r["turn_id"], r["text"]) for r in c.execute("SELECT turn_id, text FROM turns")]
        raise ValueError(f"kind phải thuộc {KINDS}")

    def _ensure(self, kind: str) -> None:
        if kind in self._mat:
            return
        items = self._source(kind)
        ids = [i for i, _ in items]
        mat = self.embedder.encode([t for _, t in items]) if items else np.zeros((0, 1), np.float32)
        self._ids[kind], self._mat[kind] = ids, mat
        self._pos[kind] = {i: p for p, i in enumerate(ids)}

    def invalidate(self, kind: str | None = None) -> None:
        with self._lock:
            for k in ([kind] if kind else list(self._mat)):
                self._mat.pop(k, None)
                self._ids.pop(k, None)
                self._pos.pop(k, None)

    def upsert(self, kind: str, items: Sequence[tuple[int, str]]) -> None:
        """Báo cho chỉ mục có mục mới / đổi văn bản. Nếu loại đó chưa nạp thì không làm gì."""
        if not items:
            return
        with self._lock:
            if kind not in self._mat:
                return
            vecs = self.embedder.encode([t for _, t in items])
            mat, ids, pos = self._mat[kind], self._ids[kind], self._pos[kind]
            new_rows = []
            for (i, _), v in zip(items, vecs):
                if i in pos:
                    mat[pos[i]] = v
                else:
                    pos[i] = len(ids)
                    ids.append(i)
                    new_rows.append(v)
            if new_rows:
                add = np.stack(new_rows)
                self._mat[kind] = add if mat.shape[0] == 0 else np.vstack([mat, add])

    def encode_query(self, text: str) -> np.ndarray:
        return self.embedder.encode([text])[0]

    def query(self, kind: str, query: str | np.ndarray, k: int = 10,
              restrict: Iterable[int] | None = None) -> list[tuple[int, float]]:
        with self._lock:
            self._ensure(kind)
            mat, ids = self._mat[kind], self._ids[kind]
        if not ids:
            return []
        q = self.encode_query(query) if isinstance(query, str) else query
        scores = mat @ q
        if restrict is not None:
            allowed = set(restrict)
            mask = np.array([i in allowed for i in ids])
            scores = np.where(mask, scores, -np.inf)
        k = min(k, len(ids))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        return [(ids[t], float(scores[t])) for t in top if np.isfinite(scores[t])]

    def all_scores(self, kind: str, query: str | np.ndarray) -> tuple[list[int], np.ndarray]:
        with self._lock:
            self._ensure(kind)
            mat, ids = self._mat[kind], list(self._ids[kind])
        if not ids:
            return [], np.zeros(0)
        q = self.encode_query(query) if isinstance(query, str) else query
        return ids, mat @ q

    def rebuild(self) -> dict[str, int]:
        """Dựng lại toàn bộ từ sổ cái (chứng minh chỉ mục là dẫn xuất)."""
        self.invalidate()
        out = {}
        for k in KINDS:
            with self._lock:
                self._ensure(k)
                out[k] = len(self._ids[k])
        return out
