"""Tổng hợp kết quả: accuracy theo 6 loại + nhóm _abs + năng lực; truy xuất; chi phí; phân loại lỗi.

    python -m ltm.eval.report data/runs/full/dev [data/runs/a1/dev ...]
Ghi thêm report.md vào thư mục của lượt chạy đầu tiên.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

from ..util import percentile
from .datasets import QTYPES


def load(run_dir: Path) -> list[dict]:
    p = Path(run_dir) / "results.jsonl"
    rows = {}
    for line in p.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            if "score" in r:
                rows[r["question_id"]] = r          # bản ghi sau cùng thắng
    return list(rows.values())


def _acc(rows: list[dict]) -> str:
    if not rows:
        return "–"
    return f"{100 * sum(r['score'] for r in rows) / len(rows):.1f} ({len(rows)})"


def _mean(xs) -> float | None:
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _fmt(x, pct=False, nd=1) -> str:
    if x is None:
        return "–"
    return f"{100 * x:.{nd}f}" if pct else f"{x:.{nd}f}"


def _tokens(u: dict) -> int:
    return sum(v.get("prompt_tokens", 0) + v.get("completion_tokens", 0)
               for k, v in (u or {}).items() if not k.startswith("_"))


def _calls(u: dict, cached: bool = False) -> int:
    return sum(v.get("calls", 0) - (v.get("cached", 0) if not cached else 0)
               for k, v in (u or {}).items() if not k.startswith("_"))


def report(run_dirs: list[Path]) -> str:
    runs = [(str(Path(d).relative_to(Path(d).parents[1])) if len(Path(d).parents) > 1 else str(d),
             load(Path(d))) for d in run_dirs]
    names = [n for n, _ in runs]
    out = ["# Kết quả LongMemEval-S", ""]

    # 1. accuracy
    head = "| Nhóm | " + " | ".join(names) + " |\n|---|" + "---|" * len(runs)
    lines = [head]
    for qt in QTYPES:
        lines.append(f"| {qt} | " + " | ".join(_acc([r for r in rs if r["question_type"] == qt])
                                             for _, rs in runs) + " |")
    lines.append("| **_abs (biết từ chối)** | " + " | ".join(
        _acc([r for r in rs if r["is_abs"]]) for _, rs in runs) + " |")
    lines.append("| không _abs | " + " | ".join(
        _acc([r for r in rs if not r["is_abs"]]) for _, rs in runs) + " |")
    lines.append("| **Tổng (micro)** | " + " | ".join(_acc(rs) for _, rs in runs) + " |")

    def macro(rs):
        vals = [sum(r["score"] for r in g) / len(g) for qt in QTYPES
                if (g := [r for r in rs if r["question_type"] == qt])]
        return f"{100 * sum(vals) / len(vals):.1f}" if vals else "–"
    lines.append("| **Macro (TB 6 loại)** | " + " | ".join(macro(rs) for _, rs in runs) + " |")
    out += ["## 1. Độ chính xác (%, số câu trong ngoặc)", "", *lines, ""]

    ab = ["| Năng lực | " + " | ".join(names) + " |", "|---|" + "---|" * len(runs)]
    for a in ("IE", "MR", "TR", "KU", "ABS"):
        ab.append(f"| {a} | " + " | ".join(_acc([r for r in rs if r.get("ability") == a])
                                          for _, rs in runs) + " |")
    out += ["### Theo 5 năng lực (IE = 3 loại single-session; ABS tách riêng)", "", *ab, ""]

    # 2. truy xuất
    rt = ["| Chỉ số | " + " | ".join(names) + " |", "|---|" + "---|" * len(runs)]
    rt.append("| Recall bộ lọc phiên (TB) | " + " | ".join(
        _fmt(_mean(r.get("filter_recall") for r in rs), True) for _, rs in runs) + " |")
    rt.append("| Recall phiên do công cụ chạm tới (TB) | " + " | ".join(
        _fmt(_mean(r.get("tool_recall") for r in rs), True) for _, rs in runs) + " |")
    rt.append("| Câu có ≥1 fact từ phiên bằng chứng | " + " | ".join(
        _fmt(_mean(1.0 if r.get("facts_in_answer_sessions") else 0.0 for r in rs
                   if r.get("answer_session_ids")), True) for _, rs in runs) + " |")
    rt.append("| Câu có ≥1 fact từ đúng LƯỢT chứa đáp án | " + " | ".join(
        _fmt(_mean((1.0 if r.get("facts_in_answer_turns") else 0.0) for r in rs
                   if r.get("n_answer_turns") and r.get("uses_facts", True)), True)
        for _, rs in runs) + " |")
    out += ["## 2. Truy xuất (%)", "", *rt, ""]

    # 3. chi phí
    cs = ["| Chỉ số (mỗi câu) | " + " | ".join(names) + " |", "|---|" + "---|" * len(runs)]

    def row(label, f):
        cs.append(f"| {label} | " + " | ".join(f(rs) for _, rs in runs) + " |")

    row("Số lần gọi công cụ TB", lambda rs: _fmt(_mean(r.get("n_tool_calls") for r in rs)))
    row("Lời gọi LLM trả lời TB", lambda rs: _fmt(_mean(r.get("n_llm_calls_answer") for r in rs)))
    row("Lời gọi LLM dựng (thật, không cache) TB", lambda rs: _fmt(_mean(
        _calls(r["build"].get("usage")) for r in rs)))
    row("Token dựng TB", lambda rs: _fmt(_mean(_tokens(r["build"].get("usage")) for r in rs), nd=0))
    row("Token trả lời TB", lambda rs: _fmt(_mean(_tokens(r["usage"]["answer"]) for r in rs), nd=0))
    row("Tỉ trọng token dựng / tổng", lambda rs: _fmt(
        (lambda b, a: b / (a + b) if (a + b) else None)(
            sum(_tokens(r["build"].get("usage")) for r in rs),
            sum(_tokens(r["usage"]["answer"]) for r in rs)), True))
    row("Độ trễ trả lời p50 / p95 (s)", lambda rs: "{} / {}".format(
        _fmt((percentile([r["answer_ms"] for r in rs], 50) or 0) / 1000),
        _fmt((percentile([r["answer_ms"] for r in rs], 95) or 0) / 1000)))
    row("Độ trễ dựng p50 / p95 (s)", lambda rs: "{} / {}".format(
        _fmt((percentile([r["build"]["ms"] for r in rs if r["build"].get("ms")], 50) or 0) / 1000),
        _fmt((percentile([r["build"]["ms"] for r in rs if r["build"].get("ms")], 95) or 0) / 1000)))
    row("Câu bị ép trả lời (hết lượt)", lambda rs: str(sum(1 for r in rs if r.get("forced"))))
    out += ["## 3. Chi phí", "", *cs,
            "", "_Token dựng chỉ tính lần dựng đầu (lượt sau dùng lại đồ thị/cache)._", ""]

    # 4. lỗi
    er = ["| Loại lỗi | " + " | ".join(names) + " |", "|---|" + "---|" * len(runs)]
    classes = ["filtered_out", "not_extracted", "tool_miss", "sql_error", "reasoning",
               "abstention_fail", "llm_error"]
    cnts = [Counter(r.get("error_class") for r in rs) for _, rs in runs]
    for c in classes:
        er.append(f"| {c} | " + " | ".join(str(k[c]) for k in cnts) + " |")
    out += ["## 4. Phân loại câu sai (tự động; 'nhầm thực thể' cần soi tay)", "", *er, ""]

    # 5. mô hình thực sự phục vụ
    out += ["## 5. Mô hình thực sự phục vụ (response.model)", ""]
    for n, rs in runs:
        served = Counter()
        mism = 0
        for r in rs:
            for u in (r["usage"]["answer"], r["usage"]["judge"], r["build"].get("usage") or {}):
                served.update(u.get("_served_models", {}))
                mism += sum(v.get("mismatch", 0) for k, v in u.items() if not k.startswith("_"))
        out.append(f"- **{n}**: {dict(served)}" + (f" — ⚠ {mism} lời gọi KHÁC mô hình yêu cầu"
                                                   if mism else ""))
    return "\n".join(out)


def main(argv: list[str]) -> None:
    dirs = [Path(a) for a in argv]
    if not dirs:
        print(__doc__)
        return
    text = report(dirs)
    (dirs[0] / "report.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main(sys.argv[1:])
