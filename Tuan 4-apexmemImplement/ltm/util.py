"""Tiện ích dùng chung: băm, ngày tháng, đọc JSON từ LLM, BM25, RRF, bảng markdown."""
from __future__ import annotations

import hashlib
import json
import math
import re
import time
from collections import Counter
from datetime import datetime
from typing import Any, Iterable, Sequence


def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def dumps(obj: Any, **kw) -> str:
    return json.dumps(obj, ensure_ascii=False, **kw)


# ---------------------------------------------------------------- ngày tháng

_LME_DATE = re.compile(r"^(\d{4})/(\d{2})/(\d{2})(?:\s*\(\w+\))?(?:\s+(\d{1,2}):(\d{2}))?")


def parse_lme_date(s: str) -> str:
    """'2023/05/20 (Sat) 02:21' -> '2023-05-20T02:21:00'. Nhận luôn chuỗi ISO."""
    s = s.strip()
    m = _LME_DATE.match(s)
    if m:
        y, mo, d, hh, mm = m.groups()
        if hh is None:
            return f"{y}-{mo}-{d}T00:00:00"
        return f"{y}-{mo}-{d}T{int(hh):02d}:{mm}:00"
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return dt.replace(tzinfo=None, microsecond=0).isoformat()


def weekday_of(iso: str) -> str:
    return datetime.fromisoformat(iso).strftime("%A")


def coerce_iso(value: Any) -> str | None:
    """Chuẩn hóa mốc thời gian LLM trả về về dạng GraphDB chấp nhận; hỏng thì None."""
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        return None
    v = value.strip()
    if re.fullmatch(r"\d{4}", v):
        return f"{v}-01-01"
    if re.fullmatch(r"\d{4}-\d{2}", v):
        return f"{v}-01"
    try:
        if len(v) == 10:
            return datetime.fromisoformat(v).date().isoformat()
        dt = datetime.fromisoformat(v.replace("Z", "+00:00"))
        return dt.replace(tzinfo=None, microsecond=0).isoformat()
    except ValueError:
        try:
            return parse_lme_date(v)
        except ValueError:
            return None


# ---------------------------------------------------------------- JSON từ LLM

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def extract_json(text: str | None) -> Any:
    """Đọc JSON từ câu trả lời LLM: chịu được ```json fences``` và chữ thừa hai đầu."""
    if text is None:
        raise ValueError("empty response")
    t = text.strip()
    m = _FENCE.search(t)
    if m:
        t = m.group(1).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    # tìm khối {...} hoặc [...] cân bằng đầu tiên
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = t.find(open_ch)
        while start != -1:
            depth, in_str, esc = 0, False, False
            for i in range(start, len(t)):
                c = t[i]
                if in_str:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_str = False
                elif c == '"':
                    in_str = True
                elif c == open_ch:
                    depth += 1
                elif c == close_ch:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(t[start:i + 1])
                        except json.JSONDecodeError:
                            break
            start = t.find(open_ch, start + 1)
    raise ValueError(f"no JSON found in: {text[:200]!r}")


# ---------------------------------------------------------------- đo thời gian

class Timer:
    def __init__(self):
        self.ms = 0.0

    def __enter__(self):
        self._t = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self.ms = (time.perf_counter() - self._t) * 1000


def percentile(xs: Sequence[float], q: float) -> float | None:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    k = (len(xs) - 1) * q / 100
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] if lo == hi else xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


# ---------------------------------------------------------------- truy xuất

_TOKEN = re.compile(r"[a-z0-9]+")
STOP = frozenset("""a an the and or of to in on at for with by from is are was were be been
being i me my we our you your he she it its they them their this that these those do does did
have has had not no so as if then than but what which who whom when where why how can could
would should will just about into over also very""".split())


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in STOP]


class BM25:
    """BM25 Okapi tối giản cho vài trăm tài liệu (dùng ở bước lọc phiên, trước khi có FTS5)."""

    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(d) for d in docs]
        self.len = [len(d) for d in docs]
        self.avg = (sum(self.len) / len(docs)) if docs else 0.0
        df = Counter(t for d in docs for t in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: list[str]) -> list[float]:
        out = []
        for tf, ln in zip(self.tf, self.len):
            s = 0.0
            for t in query:
                f = tf.get(t)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (
                        f + self.k1 * (1 - self.b + self.b * ln / (self.avg or 1)))
            out.append(s)
        return out


def rrf(rankings: Iterable[Sequence[Any]], k: int = 60) -> list[tuple[Any, float]]:
    """Reciprocal Rank Fusion (Cormack et al., 2009): chỉ dựa vào thứ hạng."""
    score: dict[Any, float] = {}
    for ranking in rankings:
        for r, item in enumerate(ranking):
            score[item] = score.get(item, 0.0) + 1.0 / (k + r + 1)
    return sorted(score.items(), key=lambda x: -x[1])


def normalize_name(s: str) -> str:
    return " ".join(re.findall(r"\w+", s.casefold()))


def truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[: max(0, n - 20)] + f" …[+{len(s) - n + 20} chars]"


def md_table(columns: Sequence[str], rows: Iterable[Sequence[Any]], cell_max: int = 200) -> str:
    def cell(v: Any) -> str:
        if v is None:
            return ""
        s = v if isinstance(v, str) else dumps(v) if isinstance(v, (list, dict)) else str(v)
        s = s.replace("|", "\\|").replace("\n", " ")
        return truncate(s, cell_max)

    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(cell(v) for v in r) + " |" for r in rows]
    return "\n".join(lines)
