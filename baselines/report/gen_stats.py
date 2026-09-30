"""Tính số liệu cho slide từ results/dev150/cases -> stats.json (chạy lại khi có thêm kết quả).

Gồm hai phần:
1. Độ chính xác theo loại câu hỏi, thời gian từng pha, danh sách câu sai.
2. Truy xuất có trúng phiên chứa bằng chứng không — dùng để tách lỗi "không tìm thấy"
   khỏi lỗi "tìm thấy nhưng suy luận sai".

Cách đối chiếu ở phần 2: mỗi ký ức LightMem trả về đều mở đầu bằng mốc thời gian của phiên
(vd "2023-05-22T23:10:00.000 Mon"), còn bộ dữ liệu cho biết ngày của từng phiên trong
haystack_dates và id phiên trong haystack_session_ids. Khớp hai mốc thời gian này là biết
ký ức được truy xuất đến từ phiên nào, rồi so với answer_session_ids.
"""
import json, glob, re, statistics as st
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

# ---- phần 2: truy xuất có trúng phiên bằng chứng không ----
SESS_DATE = re.compile(r"^(\d{4})/(\d{2})/(\d{2}) \([A-Za-z]{3}\) (\d{2}):(\d{2})")
MEM_DATE = re.compile(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})")

def sess_key(s):
    m = SESS_DATE.match(s or "")
    return f"{m[1]}-{m[2]}-{m[3]} {m[4]}:{m[5]}" if m else None

def mem_key(s):
    m = MEM_DATE.match(s or "")
    return f"{m[1]} {m[2]}" if m else None

ds = {d["question_id"]: d for d in data}
retr = []
for r in rows:
    ex = ds.get(r["question_id"])
    if not ex or not ex.get("haystack_session_ids"):
        continue
    keys = [sess_key(x) for x in ex["haystack_dates"]]
    ev = set(ex.get("answer_session_ids") or [])
    ev_keys = {k for k, sid in zip(keys, ex["haystack_session_ids"]) if k and sid in ev}
    # mốc thời gian dùng chung cho cả phiên bằng chứng lẫn phiên khác thì không kết luận chắc được
    per_key = defaultdict(set)
    for k, sid in zip(keys, ex["haystack_session_ids"]):
        per_key[k].add(sid in ev)
    got = {mem_key(m) for m in r.get("retrieved_memories", [])} - {None}
    hit_keys = ev_keys & got
    retr.append({"id": r["question_id"], "type": r["question_type"], "correct": r["correct"],
                 "hit": bool(hit_keys),
                 "ambiguous": any(len(per_key[k]) > 1 for k in hit_keys),
                 "n_ev_sessions": len(ev_keys), "n_hit": len(hit_keys)})

def rate(sel):
    s = [x for x in retr if sel(x)]
    return {"n": len(s), "hit": sum(x["hit"] for x in s)}

retr_by_type = {t: rate(lambda x, t=t: x["type"] == t) for t in order if any(x["type"] == t for x in retr)}

abs_rows = [r for r in rows if "_abs" in r["question_id"]]
wrong = [{"id": r["question_id"], "type": r["question_type"], "q": r["question"][:110],
          "gold": str(r["ground_truth"])[:70], "pred": str(r["generated_answer"]).replace("\n", " ")[:110]}
         for r in rows if not r["correct"]]
hit_map = {x["id"]: x["hit"] for x in retr}
for w in wrong:
    w["retrieved_evidence"] = hit_map.get(w["id"])
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
    "retrieval": {
        "n": len(retr),
        "hit": sum(x["hit"] for x in retr),
        "ambiguous": sum(x["ambiguous"] for x in retr),
        "by_type": retr_by_type,
        "wrong_with_evidence": sum(1 for x in retr if not x["correct"] and x["hit"]),
        "wrong_without_evidence": sum(1 for x in retr if not x["correct"] and not x["hit"]),
        "correct_with_evidence": sum(1 for x in retr if x["correct"] and x["hit"]),
        "correct_without_evidence": sum(1 for x in retr if x["correct"] and not x["hit"]),
    },
}
(Path(__file__).parent / "stats.json").write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
print(json.dumps({k: out[k] for k in ("n_done", "micro", "macro", "n_types_run")}, ensure_ascii=False))
print("truy xuat:", json.dumps(out["retrieval"], ensure_ascii=False))
