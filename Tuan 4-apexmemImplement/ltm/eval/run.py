"""Chạy đánh giá LongMemEval-S.

    python -m ltm.eval.run --config full --split dev --n 20
    python -m ltm.eval.run --config a1 --split dev          # ablation, dùng lại đồ thị đã dựng
    python -m ltm.eval.run --config simple_search_kv --split dev   # baseline, không cần đồ thị
    python -m ltm.eval.report data/runs/full/dev data/runs/a1/dev

Mỗi câu hỏi có một file đồ thị riêng data/graphs/<chữ ký dựng>/<qid>.db. Chữ ký dựng gồm mọi
tham số ảnh hưởng tới đồ thị → các cấu hình trả lời (full, a1, a2, steps*) dùng CHUNG
một đồ thị, chỉ khác cách đọc: so sánh công bằng và không tốn thêm lời gọi dựng.
Chạy lại lệnh cũ sẽ bỏ qua câu đã có kết quả (resume).
"""
from __future__ import annotations

import argparse
import json
import sys
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from ..adapters.embed import Embedder, build_embedder
from ..adapters.llm import BaseLLM, LLMFatalError, ScopedLLM, build_llm
from ..baselines.simple_search import simple_search_answer
from ..config import Cfg, load_config, resolve_path
from ..memory.relevance import filter_sessions
from ..system import MemorySystem
from ..util import dumps, sha1
from .datasets import ABILITY, EvalCase, iter_cases, make_split, read_ids, split_ids
from .judge import judge

ALL_TOOLS = ["schema_viewer", "entity_lookup", "graph_sql", "search", "property_search"]
PRESETS: dict[str, dict] = {
    # hệ đầy đủ = A3 trong Bảng 3 của bài báo (+ PropertySearch của nhóm)
    "full": {"mode": "agent", "tools": ALL_TOOLS},
    "a1": {"mode": "agent", "tools": ["schema_viewer", "entity_lookup"]},
    "a2": {"mode": "agent", "tools": ["schema_viewer", "entity_lookup", "graph_sql",
                                      "property_search"]},
    "steps10": {"mode": "agent", "tools": ALL_TOOLS, "max_steps": 10},
    "steps40": {"mode": "agent", "tools": ALL_TOOLS, "max_steps": 40},
    # Baseline SimpleSearch của LongMemEval, K = V: tìm phiên bằng lượt gốc, KHÔNG dùng fact
    # → không cần dựng đồ thị
    "simple_search_kv": {"mode": "simple", "needs_graph": False},
}
# Tăng khi đổi prompt trích xuất / giải quyết: chữ ký dựng đổi → đồ thị cũ không bị dùng nhầm.
BUILD_VERSION = 2


def build_signature(cfg: Cfg, llm: BaseLLM, embedder: Embedder) -> str:
    sig = {"v": BUILD_VERSION, "filter": dict(cfg.filter), "extract": dict(cfg.extract),
           "resolve": dict(cfg.resolve), "m_extract": llm.model_for("extract"),
           "m_resolve": llm.model_for("resolve"), "embed": embedder.model_name}
    return sha1(dumps(sig, sort_keys=True))[:10]


def _recall(found: set[str], gold: list[str]) -> float | None:
    return (len(found & set(gold)) / len(gold)) if gold else None


def build_case(case: EvalCase, cfg: Cfg, db_path: Path, llm: BaseLLM,
               embedder: Embedder, progress: bool) -> tuple[MemorySystem, dict]:
    """Dựng (hoặc dùng lại) đồ thị cho một câu hỏi. Dựng dở dang → xóa làm lại (cache LLM giúp rẻ)."""
    scope = ScopedLLM(llm)
    sysm = MemorySystem(cfg, db_path, scope, embedder)
    info = sysm.db.get_meta("build_done")
    if info:
        return sysm, info
    if sysm.db.counts()["turns"]:
        sysm.close()
        for suffix in ("", "-wal", "-shm"):
            Path(str(db_path) + suffix).unlink(missing_ok=True)
        sysm = MemorySystem(cfg, db_path, scope, embedder)
    t0 = time.perf_counter()
    f = cfg.filter
    fr = filter_sessions(case.question, case.sessions, embedder, f.get("top_sessions", 10),
                         f.get("enabled", True),
                         mode=f.get("mode"), threshold=f.get("threshold", 0.5),
                         min_sessions=f.get("min_sessions", 5),
                         max_sessions=f.get("max_sessions", 25))
    kept = {s.session_id for s in fr.kept}
    stats = sysm.builder.build_haystack(case.sessions, kept, f.get("store_all_turns", True),
                                        progress)
    info = {"stats": stats, "kept_sessions": sorted(kept),
            "n_sessions": len(case.sessions), "n_kept": len(kept),
            "filter_recall": _recall(kept, case.answer_session_ids),
            "ms": round((time.perf_counter() - t0) * 1000),
            "usage": scope.meter.snapshot()}
    sysm.db.set_meta("build_done", info)
    return sysm, info


def build_turns_only(case: EvalCase, cfg: Cfg, db_path: Path, llm: BaseLLM,
                     embedder: Embedder) -> tuple[MemorySystem, dict]:
    """Cho baseline K = V: chỉ lưu lượt gốc của mọi phiên, không trích xuất (0 lời gọi LLM)."""
    sysm = MemorySystem(cfg, db_path, ScopedLLM(llm), embedder)
    info = sysm.db.get_meta("build_done")
    if info:
        return sysm, info
    t0 = time.perf_counter()
    for s in sorted(case.sessions, key=lambda s: s.date):
        sysm.builder.add_session_turns(s)
    info = {"stats": {"sessions_built": 0, "counts": sysm.db.counts()}, "kept_sessions": [],
            "n_sessions": len(case.sessions), "n_kept": 0, "filter_recall": None,
            "ms": round((time.perf_counter() - t0) * 1000), "usage": {}}
    sysm.db.set_meta("build_done", info)
    return sysm, info


def answer_turn_keys(case: EvalCase) -> list[tuple[str, int]]:
    """(session_id, turn_index) của các lượt LongMemEval gán nhãn has_answer = chứa đáp án."""
    return [(s.session_id, i) for s in case.sessions for i, t in enumerate(s.turns)
            if t.get("has_answer")]


def facts_in_turns(sysm: MemorySystem, keys: list[tuple[str, int]]) -> int:
    """Số fact có bằng chứng trỏ ĐÚNG vào lượt chứa đáp án (chặt hơn 'cùng phiên')."""
    if not keys:
        return 0
    cond = " OR ".join("(t.session_id=? AND t.turn_index=?)" for _ in keys)
    params = [x for k in keys for x in k]
    return sysm.db.conn.execute(
        f"SELECT COUNT(DISTINCT ev.fact_id) FROM evidence ev JOIN turns t ON t.turn_id=ev.turn_id "
        f"WHERE {cond}", params).fetchone()[0]


def facts_in_sessions(sysm: MemorySystem, session_ids: list[str]) -> int:
    if not session_ids:
        return 0
    ph = ",".join("?" * len(session_ids))
    return sysm.db.conn.execute(
        f"SELECT COUNT(DISTINCT ev.fact_id) FROM evidence ev JOIN turns t ON t.turn_id=ev.turn_id "
        f"WHERE t.session_id IN ({ph})", session_ids).fetchone()[0]


def classify_error(row: dict) -> str | None:
    if row["score"] >= 0.5:
        return None
    if row.get("error"):
        return "llm_error"
    if row["is_abs"]:
        return "abstention_fail"
    if row["filter_recall"] is not None and row["filter_recall"] < 1:
        return "filtered_out"
    if row.get("uses_facts", True):
        # có nhãn lượt (has_answer) thì kiểm tra theo LƯỢT; không có thì theo phiên
        if row.get("n_answer_turns"):
            if not row.get("facts_in_answer_turns"):
                return "not_extracted"
        elif row["facts_in_answer_sessions"] == 0:
            return "not_extracted"
    if row["tool_recall"] is not None and row["tool_recall"] == 0:
        return "tool_miss"
    if row.get("sql_errors"):
        return "sql_error"
    return "reasoning"


def process_case(case: EvalCase, cfg: Cfg, preset: dict, llm: BaseLLM, embedder: Embedder,
                 graphs_dir: Path, trials: int, build_only: bool, progress: bool) -> dict:
    if preset.get("needs_graph", True):
        db_path = graphs_dir / f"{case.qid}.db"
        sysm, binfo = build_case(case, cfg, db_path, llm, embedder, progress)
    else:
        db_path = graphs_dir.parent / f"turns-only-{embedder.model_name.replace('/', '_')}" \
            / f"{case.qid}.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        sysm, binfo = build_turns_only(case, cfg, db_path, llm, embedder)
    try:
        row = {"question_id": case.qid, "question_type": case.qtype,
               "ability": "ABS" if case.is_abs else ABILITY.get(case.qtype, "?"),
               "is_abs": case.is_abs, "question": case.question, "gold": case.gold,
               "question_date": case.question_date,
               "answer_session_ids": case.answer_session_ids,
               "filter_recall": binfo.get("filter_recall"),
               "build": {k: binfo.get(k) for k in ("stats", "ms", "usage", "n_sessions")},
               "graph": str(db_path)}
        if build_only:
            return row
        ans_llm = ScopedLLM(llm)
        if preset["mode"] == "simple":
            res = simple_search_answer(sysm, case.question, case.question_date,
                                       cfg.baseline.top_sessions, llm=ans_llm)
        else:
            res = sysm.answer(case.question, case.question_date, tools=preset["tools"],
                              max_steps=preset.get("max_steps"), llm=ans_llm)
        judge_llm = ScopedLLM(llm)
        verdicts = []
        t0 = time.perf_counter()
        for tr in range(trials):
            ok, raw = judge(judge_llm, case.qtype, case.question, case.gold, res.answer or "",
                            case.is_abs, trial=tr)
            verdicts.append({"label": ok, "raw": raw[:50]})
        judge_ms = (time.perf_counter() - t0) * 1000
        seen = set(res.seen_sessions)
        row.update({
            "hypothesis": res.answer, "score": sum(v["label"] for v in verdicts) / len(verdicts),
            "verdicts": verdicts, "steps": res.steps, "n_tool_calls": len(res.steps),
            "n_llm_calls_answer": res.n_llm_calls, "forced": res.forced, "error": res.error,
            "sql_errors": res.sql_errors, "seen_sessions": sorted(seen),
            "tool_recall": _recall(seen, case.answer_session_ids),
            "facts_in_answer_sessions": facts_in_sessions(sysm, case.answer_session_ids),
            "n_answer_turns": len(answer_turn_keys(case)),
            "facts_in_answer_turns": facts_in_turns(sysm, answer_turn_keys(case)),
            "uses_facts": preset.get("needs_graph", True),
            "answer_ms": round(res.ms), "judge_ms": round(judge_ms),
            "usage": {"answer": ans_llm.meter.snapshot(), "judge": judge_llm.meter.snapshot()},
        })
        row["error_class"] = classify_error(row)
        return row
    finally:
        sysm.close()


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Đánh giá APEX-MEM trên LongMemEval-S")
    ap.add_argument("--config", default="full", choices=sorted(PRESETS))
    ap.add_argument("--config-file", default=None, help="đường dẫn config.yaml khác")
    ap.add_argument("--split", default="dev", choices=["dev", "test", "all"])
    ap.add_argument("--ids-file", default=None, help="file danh sách question_id (ghi đè --split)")
    ap.add_argument("--qtype", action="append", default=None, help="lọc theo loại (lặp được)")
    ap.add_argument("--n", type=int, default=None, help="chỉ chạy N câu đầu")
    ap.add_argument("--trials", type=int, default=None, help="số lần chấm (bài báo: 3)")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--run-name", default=None, help="tên thư mục kết quả (mặc định = split)")
    ap.add_argument("--build-only", action="store_true", help="chỉ dựng đồ thị, không trả lời")
    ap.add_argument("--progress", action="store_true", help="in tiến độ dựng từng phiên")
    args = ap.parse_args(argv)

    cfg = load_config(args.config_file)
    e = cfg.eval
    preset = PRESETS[args.config]
    trials = args.trials or e.judge_trials
    workers = args.workers or e.workers

    dataset = resolve_path(e.dataset_path)
    splits = resolve_path(e.splits_dir)
    if args.ids_file:
        ids = read_ids(args.ids_file)
    elif args.split == "all":
        ids = None
    else:
        ids = split_ids(splits, args.split)
        if ids is None:
            print(f"[split] chưa có {splits}/split.json hay {args.split}.txt → tạo mới "
                  f"(seed={e.split_seed}, dev={e.dev_size})")
            make_split(dataset, splits, e.split_seed, e.dev_size)
            ids = split_ids(splits, args.split)
    if ids is not None and args.n:
        ids = ids[: args.n]

    llm = build_llm(cfg.llm)
    embedder = build_embedder(cfg.embed)
    sig = build_signature(cfg, llm, embedder)
    graphs_dir = resolve_path(e.graphs_dir) / sig
    graphs_dir.mkdir(parents=True, exist_ok=True)
    run_dir = resolve_path(e.runs_dir) / args.config / (args.run_name or (
        Path(args.ids_file).stem if args.ids_file else args.split))
    run_dir.mkdir(parents=True, exist_ok=True)
    results_path = run_dir / "results.jsonl"
    done = set()
    if results_path.exists():
        for line in results_path.read_text(encoding="utf-8").splitlines():
            try:
                done.add(json.loads(line)["question_id"])
            except (ValueError, KeyError):
                pass
    (run_dir / "run_meta.json").write_text(dumps({
        "preset": args.config, **preset, "build_signature": sig, "graphs_dir": str(graphs_dir),
        "models": {r: llm.model_for(r) for r in ("extract", "resolve", "agent", "reader", "judge")},
        "embed": embedder.model_name, "trials": trials, "config": cfg,
        "started": time.strftime("%Y-%m-%d %H:%M:%S")}, indent=2), encoding="utf-8")

    cases = [c for c in iter_cases(dataset, ids, set(args.qtype) if args.qtype else None,
                                   args.n if ids is None else None) if c.qid not in done]
    print(f"[run] {args.config} · {len(cases)} câu cần chạy ({len(done)} đã xong) · "
          f"đồ thị: {graphs_dir} · kết quả: {run_dir}", flush=True)
    lock = threading.Lock()
    n_ok = n_all = 0

    def work(c: EvalCase) -> dict:
        try:
            return process_case(c, cfg, preset, llm, embedder, graphs_dir, trials,
                                args.build_only, args.progress and workers == 1)
        except LLMFatalError as ex:      # lỗi cấu hình: dừng cả lượt, không chạy tiếp vô ích
            return {"question_id": c.qid, "question_type": c.qtype, "is_abs": c.is_abs,
                    "fatal": str(ex), "stop": True}
        except Exception as ex:          # một câu lỗi không làm dừng cả lượt chạy
            traceback.print_exc()
            return {"question_id": c.qid, "question_type": c.qtype, "is_abs": c.is_abs,
                    "fatal": f"{type(ex).__name__}: {ex}"}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(work, c): c for c in cases}
        for i, fut in enumerate(as_completed(futs), 1):
            row = fut.result()
            if "fatal" in row:
                print(f"  [{i}/{len(cases)}] {row['question_id']} LỖI: {row['fatal']}", flush=True)
                if row.get("stop"):
                    for f in futs:
                        f.cancel()
                    print("\n[run] DỪNG: lỗi cấu hình LLM (key / tên model / quyền truy cập). "
                          "Sửa rồi chạy lại đúng lệnh này — câu đã xong được giữ nguyên.")
                    pool.shutdown(wait=False, cancel_futures=True)
                    return
                continue          # không ghi → lần chạy sau thử lại
            with lock:
                with open(results_path, "a", encoding="utf-8") as fh:
                    fh.write(dumps(row) + "\n")
                if not args.build_only:
                    with open(run_dir / "hypotheses.jsonl", "a", encoding="utf-8") as fh:
                        fh.write(dumps({"question_id": row["question_id"],
                                        "hypothesis": row["hypothesis"]}) + "\n")
                    n_all += 1
                    n_ok += row["score"] >= 0.5
            if args.build_only:
                b = row["build"]["stats"]
                print(f"  [{i}/{len(cases)}] {row['question_id']} dựng xong: {b.get('facts', 0)} "
                      f"fact · lọc recall={row['filter_recall']}", flush=True)
            else:
                print(f"  [{i}/{len(cases)}] {row['question_id']:<22} {row['question_type']:<26} "
                      f"{'ĐÚNG' if row['score'] >= 0.5 else 'SAI '} · {row['n_tool_calls']} công cụ"
                      f" · acc tạm {n_ok}/{n_all}", flush=True)
    if not args.build_only:
        from .report import report
        print(report([run_dir]))


if __name__ == "__main__":
    main(sys.argv[1:])
