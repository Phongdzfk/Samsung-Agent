"""Nạp LongMemEval-S (Wu et al., ICLR 2025) thành EvalCase; chia dev/test phân tầng theo loại.

File: longmemeval_s_cleaned.json (HF: xiaowu0162/longmemeval-cleaned). Đọc dạng stream bằng ijson
nếu có (file ~265MB) để không nạp cả bộ vào RAM.
"""
from __future__ import annotations

import json
import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from ..memory.relevance import Session
from ..util import parse_lme_date

QTYPES = ["single-session-user", "single-session-assistant", "single-session-preference",
          "multi-session", "temporal-reasoning", "knowledge-update"]
ABILITY = {"single-session-user": "IE", "single-session-assistant": "IE",
           "single-session-preference": "IE", "multi-session": "MR",
           "temporal-reasoning": "TR", "knowledge-update": "KU"}


@dataclass
class EvalCase:
    qid: str
    qtype: str
    question: str
    gold: str
    question_date: str                 # ISO
    sessions: list[Session]
    answer_session_ids: list[str]

    @property
    def is_abs(self) -> bool:
        return self.qid.endswith("_abs")


def _to_case(e: dict) -> EvalCase:
    sessions = [Session(sid, parse_lme_date(d), [t for t in turns if isinstance(t, dict)])
                for sid, d, turns in zip(e["haystack_session_ids"], e["haystack_dates"],
                                         e["haystack_sessions"])]
    return EvalCase(e["question_id"], e["question_type"], e["question"], str(e["answer"]),
                    parse_lme_date(e["question_date"]), sessions,
                    list(e.get("answer_session_ids") or []))


def _iter_raw(path: Path) -> Iterator[dict]:
    try:
        import ijson
    except ImportError:
        ijson = None
    if ijson is None:
        yield from json.loads(path.read_text(encoding="utf-8"))
        return
    with open(path, "rb") as f:
        # use_float: số thực ra float thay vì Decimal
        yield from ijson.items(f, "item", use_float=True)


def iter_cases(path: str | Path, ids: set[str] | list[str] | None = None,
               qtypes: set[str] | None = None, limit: int | None = None) -> Iterator[EvalCase]:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Không thấy {path}. Tải longmemeval_s_cleaned.json từ HuggingFace "
            "xiaowu0162/longmemeval-cleaned vào data/longmemeval/ (xem README).")
    order = list(ids) if ids is not None and not isinstance(ids, set) else None
    want = set(ids) if ids is not None else None
    n = 0
    for e in _iter_raw(path):
        if want is not None and e["question_id"] not in want:
            continue
        if qtypes and e["question_type"] not in qtypes:
            continue
        yield _to_case(e)
        n += 1
        if limit and n >= limit and order is None:
            return


def index_meta(path: str | Path) -> list[tuple[str, str]]:
    """(question_id, question_type) của toàn bộ file — nhẹ, dùng để chia tập."""
    return [(e["question_id"], e["question_type"]) for e in _iter_raw(Path(path))]


def make_split(path: str | Path, out_dir: str | Path, seed: int = 42, dev_size: int = 150
               ) -> tuple[list[str], list[str]]:
    """Chia phân tầng theo question_type, seed cố định. Ghi dev.txt / test.txt.

    Cùng thuật toán với notebook 01 (random.seed(42) → duyệt loại theo thứ tự tên → sort id →
    shuffle → lấy round(30%)) nên với 500 câu, dev=150 cho ra ĐÚNG tập dev của notebook.
    Danh sách ghi ra được sort theo id → `--n 20` lấy 20 câu trộn đủ loại, không dồn một loại.
    """
    meta = index_meta(path)
    by_type: dict[str, list[str]] = defaultdict(list)
    for qid, qt in meta:
        by_type[qt].append(qid)
    rng = random.Random(seed)
    dev: list[str] = []
    total = len(meta)
    for qt in sorted(by_type):
        ids = sorted(by_type[qt])
        rng.shuffle(ids)
        take = round(dev_size * len(ids) / total)
        dev += ids[:take]
    dev_set = set(dev)
    test = sorted(q for q, _ in meta if q not in dev_set)
    dev = sorted(dev)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "dev.txt").write_text("\n".join(dev) + "\n", encoding="utf-8")
    (out / "test.txt").write_text("\n".join(test) + "\n", encoding="utf-8")
    return dev, test


def read_ids(path: str | Path) -> list[str]:
    return [l.strip() for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def split_ids(splits_dir: str | Path, name: str) -> list[str] | None:
    """Ưu tiên split.json xuất từ notebook 01 ({"dev": [...], "test": [...]}), sau đó <name>.txt."""
    d = Path(splits_dir)
    js = d / "split.json"
    if js.exists():
        return list(json.loads(js.read_text(encoding="utf-8"))[name])
    txt = d / f"{name}.txt"
    return read_ids(txt) if txt.exists() else None
