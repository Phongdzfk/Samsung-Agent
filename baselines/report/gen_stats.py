"""Tính số liệu cho slide từ results/dev150/cases -> stats.json (chạy lại khi có thêm kết quả)."""
import json, glob, statistics as st
from collections import defaultdict, Counter
from pathlib import Path

B = Path(__file__).resolve().parent.parent
rows = [json.load(open(f, encoding="utf-8")) for f in glob.glob(str(B / "results/dev150/cases/*.json"))]
split = json.load(open(B / "data/split.json", encoding="utf-8"))
data = json.load(open(B / "data/longmemeval_s.json", encoding="utf-8"))
qtype = {d["question_id"]: d["question_type"] for d in data}
dev_n = Counter(qtype[q] for q in split["dev"])
test_n = Counter(qtype[q] for q in split["test"])

by = defaultdict(list)
for r in rows:
    by[r["question_type"]].append(r)

order = ["single-session-user", "single-session-assistant", "single-session-preference",
         "multi-session", "temporal-reasoning", "knowledge-update"]
types = []
for t in order:
    v = by.get(t, [])
    types.append({"type": t, "dev": dev_n[t], "test": test_n[t], "done": len(v),
                  "correct": sum(x["correct"] for x in v),
                  "acc": (sum(x["correct"] for x in v) / len(v)) if v else None})
ran = [t for t in types if t["done"]]
abs_rows = [r for r in rows if "_abs" in r["question_id"]]
wrong = [{"id": r["question_id"], "type": r["question_type"], "q": r["question"][:110],
          "gold": str(r["ground_truth"])[:70], "pred": str(r["generated_answer"]).replace("\n", " ")[:110]}
         for r in rows if not r["correct"]]
bt = [r["time_build_s"] / 60 for r in rows]
out = {
    "n_done": len(rows), "n_dev": len(split["dev"]), "n_test": len(split["test"]),
    "types": types,
    "micro": sum(r["correct"] for r in rows) / len(rows) if rows else None,
    "macro": (sum(t["acc"] for t in ran) / len(ran)) if ran else None,
    "n_types_run": len(ran),
    "abs": {"n": len(abs_rows), "correct": sum(r["correct"] for r in abs_rows)},
    "build_min": {"mean": st.mean(bt), "median": st.median(bt), "max": max(bt)} if bt else None,
    "retrieve_s": st.mean(r["time_retrieve_s"] for r in rows) if rows else None,
    "answer_s": st.mean(r["time_answer_s"] for r in rows) if rows else None,
    "wrong": wrong,
    "llm": rows[0]["llm_model"] if rows else "", "judge": rows[0]["judge_model"] if rows else "",
}
(Path(__file__).parent / "stats.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps({k: out[k] for k in ("n_done", "micro", "macro", "n_types_run")}, ensure_ascii=False))
