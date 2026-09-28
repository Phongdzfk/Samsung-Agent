"""Hiệu chỉnh bộ lọc phiên trên tập DEV — KHÔNG gọi LLM, chỉ cần cache embedding từ Kaggle.

    python -m ltm.eval.calibrate_filter                  # dev, mục tiêu giữ đủ bằng chứng ở 95% câu
    python -m ltm.eval.calibrate_filter --target 0.97

Vì sao cần: bài báo ghi Θ_rel = 0,2 nhưng không nói điểm tính bằng mô hình nào, thang nào →
con số đó không chép sang BGE-M3 được (cosine BGE-M3 của một cặp bất kỳ đã ~0,3–0,4).
Lọc sai là lỗi KHÔNG CỨU ĐƯỢC ở pha dựng: phiên bị bỏ thì không có fact nào từ nó.

Đo cho từng luật:
  - recall TB: tỉ lệ phiên bằng chứng (answer_session_ids) được giữ, trung bình theo câu;
  - đủ bằng chứng: % câu giữ được TẤT CẢ phiên bằng chứng (chỉ số quan trọng — câu đa phiên
    thiếu một phiên là sai);
  - số phiên giữ TB ≈ chi phí dựng (tỉ lệ thuận với số lời gọi trích xuất).
Chọn luật RẺ NHẤT đạt mục tiêu "đủ bằng chứng". Chỉ chỉnh trên dev; test khóa tới lần chạy cuối.
"""
from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from ..adapters.embed import build_embedder
from ..config import load_config, resolve_path
from ..memory.relevance import FilterResult, rank_sessions, select
from .datasets import iter_cases, make_split, split_ids

KEY_TYPES = ("multi-session", "temporal-reasoning", "knowledge-update")


def calib_dir(cfg) -> Path:
    return resolve_path(cfg.eval.runs_dir).parent / "calibration"


def collect(cfg, split: str, limit: int | None, embedder=None) -> list[dict]:
    e = cfg.eval
    out = calib_dir(cfg) / f"scores_{split}.json"
    if out.exists():
        print(f"[calibrate] dùng lại điểm đã tính: {out}")
        return json.loads(out.read_text(encoding="utf-8"))
    splits = resolve_path(e.splits_dir)
    ids = split_ids(splits, split)
    if ids is None:
        make_split(resolve_path(e.dataset_path), splits, e.split_seed, e.dev_size)
        ids = split_ids(splits, split)
    emb = embedder or build_embedder(cfg.embed)
    rows = []
    for i, c in enumerate(iter_cases(resolve_path(e.dataset_path), ids)):
        if limit and i >= limit:
            break
        if not c.answer_session_ids:
            continue
        r = rank_sessions(c.question, c.sessions, emb)
        rows.append({"qid": c.qid, "qtype": c.qtype, "gold": c.answer_session_ids,
                     "ranking": r.ranking, "dense_max": r.dense_max,
                     "n_sessions": len(c.sessions)})
        if (i + 1) % 10 == 0:
            print(f"  {i + 1} câu · cache hit {emb.stats['hit']:,} / miss {emb.stats['miss']:,}",
                  flush=True)
    if emb.stats["miss"] > 1000:
        print(f"⚠ {emb.stats['miss']:,} văn bản phải nhúng trên CPU — đã có cache Kaggle chưa?")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rows), encoding="utf-8")
    return rows


def evaluate(rows: list[dict], rule: dict) -> dict:
    rec, full, kept = [], [], []
    by_type: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        fr = FilterResult([], [tuple(x) for x in r["ranking"]], r["dense_max"])
        k = select(fr, **rule)
        g = set(r["gold"])
        hit = len(g & k) / len(g)
        rec.append(hit)
        full.append(hit == 1.0)
        kept.append(len(k))
        by_type[r["qtype"]].append(hit == 1.0)
    res = {"rule": rule, "recall": np.mean(rec), "full": np.mean(full),
           "kept": np.mean(kept), "kept_p90": float(np.percentile(kept, 90))}
    for t in KEY_TYPES:
        res[f"full_{t}"] = np.mean(by_type[t]) if by_type[t] else float("nan")
    return res


def describe(rule: dict) -> str:
    if rule["mode"] == "topk":
        return f"topk N={rule['top_sessions']}"
    return (f"threshold τ={rule['threshold']:.3f} min={rule['min_sessions']} "
            f"max={rule['max_sessions']}")


def main(argv: list[str] | None = None, cfg=None, embedder=None) -> dict | None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--target", type=float, default=0.95,
                    help="tỉ lệ câu phải giữ ĐỦ phiên bằng chứng")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args(argv)
    cfg = cfg or load_config()
    rows = collect(cfg, a.split, a.limit, embedder)
    print(f"\n{len(rows)} câu có phiên bằng chứng · TB {np.mean([r['n_sessions'] for r in rows]):.0f}"
          f" phiên/câu · TB {np.mean([len(r['gold']) for r in rows]):.2f} phiên bằng chứng/câu")

    # phân bố cosine cấp PHIÊN: bằng chứng vs không
    pos, neg = [], []
    for r in rows:
        g = set(r["gold"])
        for sid, v in r["dense_max"].items():
            (pos if sid in g else neg).append(v)
    print(f"cosine max theo phiên — bằng chứng: p10={np.percentile(pos, 10):.3f} "
          f"p50={np.median(pos):.3f} · không: p50={np.median(neg):.3f} "
          f"p90={np.percentile(neg, 90):.3f} p99={np.percentile(neg, 99):.3f}")

    rules = [{"mode": "topk", "top_sessions": n} for n in (5, 8, 10, 12, 15, 20, 25, 30)]
    lo, hi = np.percentile(neg, 50), np.percentile(pos, 50)
    for tau in np.round(np.arange(lo, hi + 1e-9, 0.01), 3):
        for mn in (3, 5, 8):
            for mx in (20, 30):
                rules.append({"mode": "threshold", "threshold": float(tau), "min_sessions": mn,
                              "max_sessions": mx})
    results = sorted((evaluate(rows, r) for r in rules), key=lambda x: (x["kept"], -x["full"]))

    out_dir = calib_dir(cfg)
    with open(out_dir / f"filter_grid_{a.split}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["rule", "recall", "full", "kept", "kept_p90", *[f"full_{t}" for t in KEY_TYPES]])
        for r in results:
            w.writerow([describe(r["rule"]), *(round(float(r[k]), 4) for k in
                        ("recall", "full", "kept", "kept_p90",
                         *[f"full_{t}" for t in KEY_TYPES]))])

    def show(title, rs):
        print(f"\n{title}\n{'luật':<42}{'recall':>8}{'đủ BC':>8}{'giữ TB':>8}{'p90':>6}"
              f"{'MS đủ':>8}{'TR đủ':>8}{'KU đủ':>8}")
        for r in rs:
            print(f"{describe(r['rule']):<42}{100 * r['recall']:>7.1f}%{100 * r['full']:>7.1f}%"
                  f"{r['kept']:>8.1f}{r['kept_p90']:>6.0f}"
                  + "".join(f"{100 * r[f'full_{t}']:>7.1f}%" if r[f"full_{t}"] == r[f"full_{t}"]
                            else f"{'–':>8}" for t in KEY_TYPES))

    show("TOP-K", [r for r in results if r["rule"]["mode"] == "topk"])
    ok = [r for r in results if r["full"] >= a.target]
    best_thr = [r for r in ok if r["rule"]["mode"] == "threshold"][:8]
    show(f"NGƯỠNG — 8 luật rẻ nhất đạt 'đủ bằng chứng' ≥ {100 * a.target:.0f}%", best_thr)
    if not ok:
        print(f"\nKhông luật nào đạt {100 * a.target:.0f}% — hạ --target hoặc tăng max_sessions.")
        return None
    best = ok[0]
    topk_ok = [r for r in ok if r["rule"]["mode"] == "topk"]
    print(f"\n→ ĐỀ XUẤT: {describe(best['rule'])}: giữ TB {best['kept']:.1f} phiên, "
          f"đủ bằng chứng {100 * best['full']:.1f}%")
    if topk_ok and best["rule"]["mode"] == "threshold":
        t = topk_ok[0]
        print(f"   (top-k rẻ nhất đạt mục tiêu: {describe(t['rule'])}, giữ {t['kept']:.1f} phiên — "
              f"ngưỡng tiết kiệm {100 * (1 - best['kept'] / t['kept']):.0f}% lời gọi trích xuất)")
    rule = best["rule"]
    print("\nDán vào config.yaml:\nfilter:\n  enabled: true")
    for k, v in rule.items():
        print(f"  {k}: {v}")
    print(f"\nBảng đầy đủ: {out_dir / f'filter_grid_{a.split}.csv'}")
    return best


if __name__ == "__main__":
    main()
