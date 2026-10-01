"""So sánh APEX-MEM (full) với LightMem trên cùng các câu dev -> compare.json.

Đọc:
  - baselines/results/apexmem-full-dev/results.jsonl   (APEX-MEM, copy từ Tuan 4-apexmemImplement/data/runs/full/dev)
  - baselines/results/dev150/cases/*.json              (LightMem)

Chỉ so trên các câu có kết quả ở CẢ HAI hệ, cùng model trả lời (cx/gpt-5.6-luna), cùng model chấm
(cx/gpt-5.6-terra), cùng prompt chấm chính thức của LongMemEval, cùng tập dev (seed 42).
"""
import glob
import json
import math
import statistics as st
from collections import defaultdict
from pathlib import Path

B = Path(__file__).resolve().parent.parent
ORDER = ["single-session-user", "single-session-assistant", "single-session-preference",
         "multi-session", "temporal-reasoning", "knowledge-update"]

apex = {}
for line in open(B / "results/apexmem-full-dev/results.jsonl", encoding="utf-8"):
    if line.strip():
        r = json.loads(line)
        apex[r["question_id"]] = r
lm = {}
for f in glob.glob(str(B / "results/dev150/cases/*.json")):
    r = json.load(open(f, encoding="utf-8"))
    lm[r["question_id"]] = r

ids = sorted(q for q in apex if q in lm)
a_ok = {q: bool(apex[q].get("score")) for q in ids}
l_ok = {q: bool(lm[q]["correct"]) for q in ids}
qt = {q: apex[q]["question_type"] for q in ids}


def wilson(k, n, z=1.96):
    if n == 0:
        return None
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [max(0.0, c - h), min(1.0, c + h)]


def mcnemar_exact(b, c):
    """Kiểm định dấu hai phía, chính xác (nhị thức) cho cặp không khớp b, c."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    p = sum(math.comb(n, i) for i in range(0, k + 1)) / 2 ** n
    return min(1.0, 2 * p)


both = sum(1 for q in ids if a_ok[q] and l_ok[q])
only_a = sum(1 for q in ids if a_ok[q] and not l_ok[q])
only_l = sum(1 for q in ids if l_ok[q] and not a_ok[q])
neither = sum(1 for q in ids if not a_ok[q] and not l_ok[q])

by = {}
for t in ORDER:
    s = [q for q in ids if qt[q] == t]
    if not s:
        continue
    by[t] = {"n": len(s), "apex": sum(a_ok[q] for q in s), "lm": sum(l_ok[q] for q in s),
             "only_apex": sum(1 for q in s if a_ok[q] and not l_ok[q]),
             "only_lm": sum(1 for q in s if l_ok[q] and not a_ok[q])}
    by[t]["apex_acc"], by[t]["lm_acc"] = by[t]["apex"] / len(s), by[t]["lm"] / len(s)

n = len(ids)
absq = [q for q in ids if "_abs" in q]

# ---- chi phí / thời gian của APEX-MEM (đo trực tiếp từ results.jsonl) ----
def tokens(r):
    u = ((r.get("build") or {}).get("usage")) or {}
    return sum(v.get("prompt_tokens", 0) + v.get("completion_tokens", 0)
               for v in u.values() if isinstance(v, dict))

build_tok = [tokens(apex[q]) for q in ids]
build_min = [(apex[q].get("build") or {}).get("ms", 0) / 60000 for q in ids]
ans_s = [(apex[q].get("answer_ms") or 0) / 1000 for q in ids]
lm_build_min = [lm[q]["time_build_s"] / 60 for q in ids]
lm_ans_s = [lm[q]["time_answer_s"] for q in ids]

# ---- câu hai hệ khác nhau, để soi định tính ----
def brief(q):
    return {"id": q, "type": qt[q], "q": apex[q]["question"][:120],
            "gold": str(apex[q].get("gold"))[:80],
            "apex": str(apex[q].get("hypothesis")).replace("\n", " ")[:140],
            "lm": str(lm[q]["generated_answer"]).replace("\n", " ")[:140]}

diff_apex_right = [brief(q) for q in ids if a_ok[q] and not l_ok[q]]
diff_lm_right = [brief(q) for q in ids if l_ok[q] and not a_ok[q]]
both_wrong = [brief(q) for q in ids if not a_ok[q] and not l_ok[q]]

apex_wrong_class = defaultdict(int)
for q in ids:
    if not a_ok[q]:
        apex_wrong_class[apex[q].get("error_class") or "?"] += 1

import re


def parse_report(path):
    """Lấy số chi phí từ report.md do ltm.eval.report sinh ra (không tự tính lại, tránh lệch)."""
    t = open(path, encoding="utf-8-sig").read()
    num = lambda pat: float(re.search(pat, t).group(1).replace(",", ""))  # noqa: E731
    two = lambda pat: [float(x) for x in re.search(pat, t).groups()]       # noqa: E731
    served = dict(re.findall(r"'(gpt-[\w.\-]+)': (\d+)", t))
    return {
        "build_tokens": num(r"Token dựng TB \| ([\d.,]+)"),
        "answer_tokens": num(r"Token trả lời TB \| ([\d.,]+)"),
        "build_share": num(r"Tỉ trọng token dựng / tổng \| ([\d.]+)"),
        "build_calls": num(r"Lời gọi LLM dựng \(thật, không cache\) TB \| ([\d.]+)"),
        "answer_calls": num(r"Lời gọi LLM trả lời TB \| ([\d.]+)"),
        "tool_calls": num(r"Số lần gọi công cụ TB \| ([\d.]+)"),
        "build_lat_p50_p95_s": two(r"Độ trễ dựng p50 / p95 \(s\) \| ([\d.]+) / ([\d.]+)"),
        "answer_lat_p50_p95_s": two(r"Độ trễ trả lời p50 / p95 \(s\) \| ([\d.]+) / ([\d.]+)"),
        "filter_recall": num(r"Recall bộ lọc phiên \(TB\) \| ([\d.]+)"),
        "tool_recall": num(r"Recall phiên do công cụ chạm tới \(TB\) \| ([\d.]+)"),
        "served_models": {k: int(v) for k, v in served.items()},
    }


apex_report = parse_report(B / "results/apexmem-full-dev/report.md")
macro = lambda key: sum(v[key] for v in by.values()) / len(by)  # noqa: E731
out = {
    "n": n,
    "apex": {"correct": sum(a_ok.values()), "micro": sum(a_ok.values()) / n, "macro": macro("apex_acc"),
             "ci95": wilson(sum(a_ok.values()), n)},
    "lm": {"correct": sum(l_ok.values()), "micro": sum(l_ok.values()) / n, "macro": macro("lm_acc"),
           "ci95": wilson(sum(l_ok.values()), n)},
    "paired": {"both_right": both, "only_apex": only_a, "only_lm": only_l, "both_wrong": neither,
               "mcnemar_p": mcnemar_exact(only_a, only_l)},
    "by_type": by,
    "abs": {"n": len(absq), "apex": sum(a_ok[q] for q in absq), "lm": sum(l_ok[q] for q in absq)},
    "apex_wrong_class": dict(apex_wrong_class),
    "apex_report": apex_report,
    "lm_cost": {"build_min_p95": sorted(lm_build_min)[int(0.95 * (len(lm_build_min) - 1))], "build_min_median": st.median(lm_build_min), "build_min_mean": st.mean(lm_build_min),
                "build_min_max": max(lm_build_min), "answer_s_median": st.median(lm_ans_s)},
    "diff_apex_right": diff_apex_right,
    "diff_lm_right": diff_lm_right,
    "both_wrong": both_wrong,
}
(Path(__file__).parent / "compare.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"{n} câu chung | APEX {out['apex']['correct']}/{n} = {out['apex']['micro']:.1%} (macro {out['apex']['macro']:.1%}) "
      f"| LightMem {out['lm']['correct']}/{n} = {out['lm']['micro']:.1%} (macro {out['lm']['macro']:.1%})")
print("cặp:", out["paired"])
print("theo loại:")
for t, v in by.items():
    print(f"  {t:28s} n={v['n']:3d}  APEX {v['apex']:3d}  LM {v['lm']:3d}   (chỉ APEX đúng {v['only_apex']}, chỉ LM đúng {v['only_lm']})")
print("_abs:", out["abs"], "| APEX sai theo lớp:", out["apex_wrong_class"])
