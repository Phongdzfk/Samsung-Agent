"""Bước 1 luồng ghi — lọc phiên liên quan (không gọi LLM).

APEX-MEM dựng bộ nhớ "online" trên LongMemEval: chỉ trích xuất từ các phiên có
Relevance(d_i|Q) > Θ_rel (bài báo ghi Θ_rel = 0,2 nhưng KHÔNG nêu điểm đó tính bằng mô hình nào,
thang đo nào) → không chép được con số 0,2; phải hiệu chỉnh ngưỡng trên thang điểm của mình
(xem ltm/eval/calibrate_filter.py).

Hai tín hiệu cho mỗi phiên:
  - dense_max: cosine LỚN NHẤT giữa câu hỏi và các lượt của phiên (BGE-M3) — có thang đo tuyệt
    đối nên đặt ngưỡng được;
  - BM25 trên toàn văn phiên — chỉ dùng qua thứ hạng (RRF), vì điểm BM25 không so được giữa
    các câu hỏi.

Ba chế độ (filter.mode):
  - "topk":      giữ top_sessions phiên theo RRF(dense, BM25).
  - "threshold": giữ phiên có dense_max >= threshold, nhưng luôn ít nhất min_sessions (theo
                 RRF, để BM25 cứu các câu trùng từ khóa) và nhiều nhất max_sessions. Số phiên giữ
                 tự co giãn: câu đa phiên / thời gian giữ nhiều hơn, câu một phiên giữ ít hơn.
  - "all":       không lọc.
Kết quả trả theo thứ tự thời gian để dựng đồ thị đúng trình tự.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..adapters.embed import Embedder
from ..util import BM25, rrf, tokenize


@dataclass
class Session:
    session_id: str
    date: str                   # ISO 8601
    turns: list[dict]           # [{"role","content", "has_answer"?}]


@dataclass
class FilterResult:
    kept: list[Session]
    ranking: list[tuple[str, float]] = field(default_factory=list)   # (sid, điểm RRF) giảm dần
    dense_max: dict[str, float] = field(default_factory=dict)


def rank_sessions(question: str, sessions: list[Session], embedder: Embedder) -> FilterResult:
    if not sessions:
        return FilterResult([])
    texts, owner = [], []
    for s in sessions:
        for t in s.turns:
            if t.get("content"):
                texts.append(t["content"])
                owner.append(s.session_id)
    q = embedder.encode([question])[0]
    sims = embedder.encode(texts) @ q if texts else np.zeros(0)
    dense_max: dict[str, float] = {s.session_id: -1.0 for s in sessions}
    for sid, v in zip(owner, sims):
        dense_max[sid] = max(dense_max[sid], float(v))
    dense_rank = sorted(dense_max, key=lambda s: -dense_max[s])

    bm = BM25([tokenize(" ".join(t.get("content") or "" for t in s.turns)) for s in sessions])
    bs = bm.scores(tokenize(question))
    lex_rank = [sessions[i].session_id for i in np.argsort(-np.asarray(bs), kind="stable")]
    return FilterResult([], rrf([dense_rank, lex_rank]), dense_max)


def select(res: FilterResult, mode: str = "topk", top_sessions: int = 10,
           threshold: float = 0.5, min_sessions: int = 5, max_sessions: int = 25) -> set[str]:
    """Chọn tập phiên từ điểm đã tính — tách riêng để hiệu chỉnh quét nhiều luật không phải nhúng lại."""
    order = [sid for sid, _ in res.ranking]
    if mode == "all":
        return set(order)
    if mode == "topk":
        return set(order[:top_sessions])
    if mode == "threshold":
        # duyệt theo hạng RRF: phiên vượt ngưỡng luôn giữ; phiên dưới ngưỡng chỉ giữ để lấp cho
        # đủ min_sessions; dừng khi đạt max_sessions (bỏ phần hạng thấp)
        above = sum(1 for sid in order if res.dense_max.get(sid, -1) >= threshold)
        fill = max(0, min_sessions - above)
        keep: list[str] = []
        for sid in order:
            if len(keep) >= max_sessions:
                break
            if res.dense_max.get(sid, -1) >= threshold:
                keep.append(sid)
            elif fill > 0:
                keep.append(sid)
                fill -= 1
        return set(keep)
    raise ValueError(f"filter.mode không hợp lệ: {mode}")


def filter_sessions(question: str, sessions: list[Session], embedder: Embedder,
                    top_n: int = 10, enabled: bool = True, *, mode: str | None = None,
                    threshold: float = 0.5, min_sessions: int = 5,
                    max_sessions: int = 25) -> FilterResult:
    mode = mode or ("topk" if enabled else "all")
    if mode == "all":
        return FilterResult(sorted(sessions, key=lambda s: s.date))
    res = rank_sessions(question, sessions, embedder)
    keep = select(res, mode, top_n, threshold, min_sessions, max_sessions)
    res.kept = sorted((s for s in sessions if s.session_id in keep), key=lambda s: s.date)
    return res
