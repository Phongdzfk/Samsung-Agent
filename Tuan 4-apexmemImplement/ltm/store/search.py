"""Tìm kiếm lai dense + FTS5 (BM25 của SQLite), hợp nhất bằng RRF — dùng chung cho các công cụ."""
from __future__ import annotations

from ..util import rrf
from .graphdb import GraphDB
from .vector import VectorIndex

FTS_KIND = {"turn": "turns", "entity": "entities", "fact": "facts"}


def hybrid_search(db: GraphDB, index: VectorIndex, kind: str, query: str, k: int = 10,
                  pool: int = 30) -> list[tuple[int, float]]:
    """Trả [(id, điểm RRF)]. Loại không có FTS (property) thì chỉ dùng dense."""
    dense = [i for i, _ in index.query(kind, query, pool)]
    lists = [dense]
    if kind in FTS_KIND:
        lists.append([i for i, _ in db.search_lexical(FTS_KIND[kind], query, pool)])
    return rrf(lists)[:k]
