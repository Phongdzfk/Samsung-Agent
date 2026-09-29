"""Test bộ đánh giá đầu–cuối trên một LongMemEval thu nhỏ (cùng định dạng file thật)."""
import json

import pytest

from ltm.demo.export_html import export
from ltm.eval import run as runmod
from ltm.eval.datasets import iter_cases, make_split, read_ids
from ltm.eval.report import report

from fakes import make_cfg, make_embedder, make_llm


def entry(qid, qtype, q, a, sessions, answer_ids):
    return {"question_id": qid, "question_type": qtype, "question": q, "answer": a,
            "question_date": "2024/02/01 (Thu) 10:00",
            "haystack_session_ids": [s[0] for s in sessions],
            "haystack_dates": [s[1] for s in sessions],
            "haystack_sessions": [s[2] for s in sessions],
            "answer_session_ids": answer_ids}


SESS = [("s1", "2023/03/10 (Fri) 10:00", [{"role": "user", "content": "I passed JLPT N5 today"},
                                          {"role": "assistant", "content": "Congrats!"}]),
        ("s2", "2024/01/22 (Mon) 09:00", [{"role": "user", "content": "My JLPT level is N4 now",
                                           "has_answer": True},
                                          {"role": "assistant", "content": "Great!"}]),
        ("s3", "2023/06/01 (Thu) 09:00", [{"role": "user", "content": "Pancake recipe please"},
                                          {"role": "assistant", "content": "Flour and eggs."}])]


@pytest.fixture
def dataset(tmp_path):
    data = [entry("q1", "knowledge-update", "What is my current JLPT level?", "N4", SESS,
                  ["s2"]),
            entry("q2", "single-session-user", "What level did I pass first?", "N5", SESS,
                  ["s1"]),
            entry("q3_abs", "single-session-user", "What is my cat's name?",
                  "You did not mention a cat", SESS, [])]
    (tmp_path / "lme.json").write_text(json.dumps(data))
    return tmp_path


def test_loader_parses_dates_and_abs(dataset):
    cases = list(iter_cases(dataset / "lme.json"))
    assert [c.qid for c in cases] == ["q1", "q2", "q3_abs"]
    assert cases[0].question_date == "2024-02-01T10:00:00"
    assert cases[0].sessions[1].date == "2024-01-22T09:00:00"
    assert cases[2].is_abs and not cases[0].is_abs
    assert [c.qid for c in iter_cases(dataset / "lme.json", ids=["q2"])] == ["q2"]


def test_split_is_stratified_and_disjoint(dataset):
    dev, test = make_split(dataset / "lme.json", dataset / "splits", seed=1, dev_size=2)
    assert set(dev).isdisjoint(test) and len(dev) + len(test) == 3
    assert read_ids(dataset / "splits" / "dev.txt") == dev


@pytest.fixture
def patched(dataset, monkeypatch):
    cfg = make_cfg(dataset, filter={"top_sessions": 2})
    monkeypatch.setattr(runmod, "load_config", lambda *a, **k: cfg)
    monkeypatch.setattr(runmod, "build_llm", lambda c: make_llm())
    monkeypatch.setattr(runmod, "build_embedder", lambda c: make_embedder())
    (dataset / "ids.txt").write_text("q1\nq2\nq3_abs\n")
    return dataset


def rows_of(path):
    return [json.loads(l) for l in path.read_text().splitlines()]


def test_run_full_then_ablation_reuses_graph(patched, capsys):
    d = patched
    runmod.main(["--config", "full", "--ids-file", str(d / "ids.txt")])
    res = rows_of(d / "runs" / "full" / "ids" / "results.jsonl")
    by = {r["question_id"]: r for r in res}
    assert by["q1"]["hypothesis"] == "N4" and by["q1"]["score"] == 1.0
    assert by["q3_abs"]["score"] == 1.0 and by["q3_abs"]["ability"] == "ABS"
    assert by["q1"]["filter_recall"] == 1.0 and by["q1"]["tool_recall"] == 1.0
    assert by["q2"]["error_class"] in ("reasoning", "tool_miss", None)
    hyp = rows_of(d / "runs" / "full" / "ids" / "hypotheses.jsonl")
    assert {h["question_id"] for h in hyp} == {"q1", "q2", "q3_abs"}     # định dạng chính thức
    assert by["q1"]["build"]["usage"]["extract"]["calls"] >= 1

    graphs = list((d / "graphs").glob("*/*.db"))
    assert len(graphs) == 3
    mtimes = {p: p.stat().st_mtime_ns for p in graphs}

    # ablation a1 + baseline: không dựng lại đồ thị, không gọi extract
    runmod.main(["--config", "a1", "--ids-file", str(d / "ids.txt")])
    runmod.main(["--config", "simple_search", "--ids-file", str(d / "ids.txt")])
    a1 = rows_of(d / "runs" / "a1" / "ids" / "results.jsonl")
    assert all("extract" not in r["usage"]["answer"] for r in a1)
    ss = rows_of(d / "runs" / "simple_search" / "ids" / "results.jsonl")
    assert {r["question_id"] for r in ss} == {"q1", "q2", "q3_abs"}
    assert len(list((d / "graphs").glob("*/*.db"))) == 3

    # resume: chạy lại không làm gì thêm
    runmod.main(["--config", "full", "--ids-file", str(d / "ids.txt")])
    assert len(rows_of(d / "runs" / "full" / "ids" / "results.jsonl")) == 3

    txt = report([d / "runs" / "full" / "ids", d / "runs" / "a1" / "ids"])
    assert "knowledge-update" in txt and "Macro" in txt and "_abs" in txt
    out = export([d / "runs" / "full" / "ids"], d / "demo.html")
    html = out.read_text(encoding="utf-8")
    assert "What is my current JLPT level?" in html and "<script>" in html


def test_build_only(patched):
    d = patched
    runmod.main(["--config", "full", "--ids-file", str(d / "ids.txt"), "--build-only"])
    rows = rows_of(d / "runs" / "full" / "ids" / "results.jsonl")
    assert all("hypothesis" not in r for r in rows)


def test_calibrate_filter_recommends_rule(patched, capsys):
    from ltm.eval import calibrate_filter as cal
    cfg = runmod.load_config()
    (patched / "splits").mkdir(exist_ok=True)
    (patched / "splits" / "dev.txt").write_text("q1\nq2\nq3_abs\n")
    best = cal.main(["--target", "0.5"], cfg=cfg, embedder=make_embedder())
    out = capsys.readouterr().out
    assert best is not None and "ĐỀ XUẤT" in out and "TOP-K" in out
    assert (patched / "calibration" / "filter_grid_dev.csv").exists()
    assert (patched / "calibration" / "scores_dev.json").exists()       # lần sau không nhúng lại


def test_model_not_found_stops_run_without_writing(patched, monkeypatch):
    from ltm.adapters.llm import LLMFatalError

    def boom(messages, tools):
        raise LLMFatalError("model 'cx/gpt-5.5' không dùng được")
    monkeypatch.setattr(runmod, "build_llm", lambda c: make_llm(extract=boom))
    runmod.main(["--config", "full", "--ids-file", str(patched / "ids.txt"), "--workers", "1"])
    res = patched / "runs" / "full" / "ids" / "results.jsonl"
    assert not res.exists() or res.read_text().strip() == ""
    # đồ thị dở dang KHÔNG bị đánh dấu xong → lần sau dựng lại
    from ltm.store.graphdb import GraphDB
    for db in (patched / "graphs").glob("*/*.db"):
        g = GraphDB(db)
        assert g.get_meta("build_done") is None
        g.close()
