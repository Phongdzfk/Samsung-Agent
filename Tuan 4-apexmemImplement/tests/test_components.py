"""Test từng thành phần: kiểm tra fact, LLM adapter (cache, retry, phát hiện đổi mô hình), judge."""
import json

import pytest

from ltm.adapters.embed import EmbedCache, HashEmbedder
from ltm.adapters.llm import (FakeLLM, LLMCache, LLMJSONError, LLMResponse, ModelMismatchError,
                              OpenAICompatLLM, same_model)
from ltm.eval.judge import judge, judge_prompt
from ltm.memory.extractor import FactExtractor, coerce_value, normalize_property, Rejected
from ltm.store.graphdb import DEFAULT_ONTOLOGY
from ltm.util import extract_json, parse_lme_date


# ---------------------------------------------------------------- tiện ích

def test_parse_lme_date():
    assert parse_lme_date("2023/05/20 (Sat) 02:21") == "2023-05-20T02:21:00"
    assert parse_lme_date("2023/05/20") == "2023-05-20T00:00:00"


def test_extract_json_tolerates_fences_and_noise():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! {"a": {"b": "}"}} hope it helps') == {"a": {"b": "}"}}
    with pytest.raises(ValueError):
        extract_json("no json here")


# ---------------------------------------------------------------- kiểm tra fact

@pytest.mark.parametrize("raw,expected,fixed", [
    ("japanese_level", "japanese_level", False),
    ("Japanese Level", "japanese_level", True),
    ("home-city", "home_city", True),
])
def test_normalize_property(raw, expected, fixed):
    assert normalize_property(raw) == (expected, fixed)


@pytest.mark.parametrize("raw,reason", [("trình_độ", "property_not_ascii"),
                                        ("2nd_language", "property_bad_format"),
                                        ("", "property_empty")])
def test_normalize_property_rejects(raw, reason):
    with pytest.raises(Rejected) as e:
        normalize_property(raw)
    assert e.value.reason == reason


@pytest.mark.parametrize("value,dtype,out", [
    ("3", "int", (3, "int")), ("2.5", "int", (2.5, "float")), ("about three", "int",
                                                                ("about three", "str")),
    ("yes", "bool", (True, "bool")), ("2024-01-22T10:00:00", "date", ("2024-01-22", "date")),
    ("a", "list", (["a"], "list")), ("example.com", "url", ("example.com", "str")),
])
def test_coerce_value(value, dtype, out):
    assert coerce_value(value, dtype) == out


def test_extractor_parse_counts_rejections():
    x = FactExtractor(FakeLLM(), DEFAULT_ONTOLOGY)
    raw = {"events": [{"type": "Exam Result", "anchor_datetime": "2024-01-20",
                       "participants": [{"name": "User", "type": "Person", "role": "Speaker"},
                                        {"name": "JLPT", "type": "Weird", "role": "Boss"}],
                       "facts": [
                           {"subject": "User", "property": "Japanese Level", "dtype": "enum",
                            "value": "N4", "evidence_turn": 1},
                           {"subject": "User", "property": "trình_độ", "dtype": "str",
                            "value": "x", "evidence_turn": 1},
                           {"subject": "User", "property": "age", "dtype": "int",
                            "value": 30, "evidence_turn": 99},
                           {"subject": "User", "property": "age", "dtype": "int",
                            "value": None, "evidence_turn": 1}]}]}
    stats = {}
    evs, rej = x.parse(raw, "2024-01-22T00:00:00", {0, 1}, stats)
    assert len(evs) == 1 and evs[0].type == "exam_result"
    f = evs[0].facts[0]
    assert (f.property, f.value, f.t_from) == ("japanese_level", "N4", "2024-01-20")
    assert evs[0].participants[1] == ("JLPT", "Other", "Mentioned")
    assert sorted(r["reason"] for r in rej) == ["bad_evidence_turn", "property_not_ascii",
                                                "value_empty"]
    assert stats["normalized_property"] == 1


def test_extractor_survives_llm_garbage():
    llm = FakeLLM({"extract": ["not json", "still not json"]})
    x = FactExtractor(llm, DEFAULT_ONTOLOGY)
    evs, rej, st = x.extract_session("2024-01-01T00:00:00", [(0, "user", "hi")])
    assert evs == [] and st["llm_failed"] == 1 and rej[0]["reason"] == "llm_failed"


def test_complete_json_retries_once():
    llm = FakeLLM({"x": ["oops", '{"ok": true}']})
    assert llm.complete_json("p", role="x") == {"ok": True}
    llm = FakeLLM({"x": ["oops", "oops"]})
    with pytest.raises(LLMJSONError):
        llm.complete_json("p", role="x")


# ---------------------------------------------------------------- adapter thật (không gọi mạng)

def test_same_model():
    assert same_model("cx/gpt-5.5", "gpt-5.5")
    assert same_model("cx/gpt-5.5", "gpt-5.5-2026-04-23")
    assert same_model("cx/gpt-5.5", "")
    assert not same_model("cx/gpt-5.5", "glm-5.1")


@pytest.fixture
def real_llm(tmp_path, monkeypatch):
    cfg = {"base_url": "http://localhost:1/v1", "api_key_env": "X", "model": "cx/gpt-5.5",
           "roles": {"judge": "cx/gpt-5.4"}, "strict_model": False}
    llm = OpenAICompatLLM(cfg, cache=LLMCache(tmp_path / "c.db"))
    calls = []

    def fake_call(messages, tools, params):
        calls.append(params["model"])
        served = llm._served if hasattr(llm, "_served") else params["model"].split("/")[-1]
        return LLMResponse("hello", [], served, {"prompt_tokens": 5, "completion_tokens": 2}, 10)

    monkeypatch.setattr(llm, "_call", fake_call)
    llm.calls = calls
    return llm


def test_cache_prevents_second_call(real_llm):
    m = [{"role": "user", "content": "hi"}]
    a = real_llm.chat(m, role="agent")
    b = real_llm.chat(m, role="agent")
    assert a.content == b.content == "hello" and b.cached and len(real_llm.calls) == 1
    real_llm.chat(m, role="agent", salt="trial-2")               # salt khác → gọi lại
    assert len(real_llm.calls) == 2
    snap = real_llm.meter.snapshot()
    assert snap["agent"]["calls"] == 3 and snap["agent"]["cached"] == 1


def test_role_models(real_llm):
    real_llm.chat([{"role": "user", "content": "x"}], role="judge")
    assert real_llm.calls == ["cx/gpt-5.4"]


def test_model_mismatch_detected_and_not_cached(real_llm):
    real_llm._served = "glm-5.1"                                  # router lén đổi mô hình
    m = [{"role": "user", "content": "hi"}]
    real_llm.chat(m, role="agent")
    assert real_llm.meter.snapshot()["agent"]["mismatch"] == 1
    real_llm.chat(m, role="agent")
    assert len(real_llm.calls) == 2                               # không cache câu trả lời sai mô hình
    real_llm.cfg["strict_model"] = True
    with pytest.raises(ModelMismatchError):
        real_llm.chat([{"role": "user", "content": "new"}], role="agent")


def test_retry_on_rate_limit(tmp_path, monkeypatch):
    import httpx
    import openai

    llm = OpenAICompatLLM({"base_url": "http://localhost:1/v1", "model": "cx/gpt-5.5",
                           "max_retries": 3, "max_wait": 0.01}, cache=None)
    llm.cache = None
    n = {"i": 0}
    req = httpx.Request("POST", "http://localhost:1/v1/chat/completions")

    def flaky(messages, tools, params):
        n["i"] += 1
        if n["i"] < 3:
            raise openai.RateLimitError("all accounts exhausted",
                                        response=httpx.Response(429, request=req), body=None)
        return LLMResponse("ok", [], "gpt-5.5", {}, 1)

    monkeypatch.setattr(llm, "_call", flaky)
    monkeypatch.setattr("time.sleep", lambda s: None)
    assert llm.chat([{"role": "user", "content": "x"}]).content == "ok" and n["i"] == 3


# ---------------------------------------------------------------- embedding cache

def test_embed_cache_roundtrip(tmp_path):
    cache = EmbedCache(tmp_path / "e.db")
    e1 = HashEmbedder(cache=cache)
    v1 = e1.encode(["hello world", "hello world", "other"])
    assert e1.stats["miss"] == 2
    e2 = HashEmbedder(cache=cache)
    v2 = e2.encode(["hello world"])
    assert e2.stats == {"hit": 1, "miss": 0}
    assert abs(float(v1[0] @ v2[0]) - 1.0) < 1e-3               # float16 vẫn đủ chính xác


# ---------------------------------------------------------------- judge

def test_judge_prompt_variants():
    assert "off-by-one" in judge_prompt("temporal-reasoning", "q", "a", "r", False)
    assert "updated answer" in judge_prompt("knowledge-update", "q", "a", "r", False)
    assert "Rubric: a" in judge_prompt("single-session-preference", "q", "a", "r", False)
    assert "unanswerable" in judge_prompt("multi-session", "q", "a", "r", True)


def test_judge_label_is_yes_in_response():
    ok, raw = judge(FakeLLM({"judge": "Yes."}), "multi-session", "q", "a", "r", False)
    assert ok and raw == "Yes."



def test_retries_exhausted_is_fatal(monkeypatch):
    import httpx
    import openai
    from ltm.adapters.llm import LLMFatalError

    llm = OpenAICompatLLM({"base_url": "http://localhost:1/v1", "model": "m", "max_retries": 2,
                           "max_wait": 0.01}, cache=None)
    llm.cache = None
    req = httpx.Request("POST", "http://localhost:1/v1/chat/completions")

    def always_429(messages, tools, params):
        raise openai.RateLimitError("quota", response=httpx.Response(429, request=req), body=None)

    monkeypatch.setattr(llm, "_call", always_429)
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(LLMFatalError):
        llm.chat([{"role": "user", "content": "x"}])


def test_rpm_pacing(monkeypatch):
    llm = OpenAICompatLLM({"base_url": "http://localhost:1/v1", "model": "m", "rpm": 60}, cache=None)
    slept = []
    monkeypatch.setattr("time.sleep", lambda s: slept.append(s))
    for _ in range(3):
        llm._pace()
    assert len(slept) == 2 and all(0.9 < s <= 2.01 for s in slept)


def test_extraction_prompt_asks_for_place_companion_units():
    x = FactExtractor(FakeLLM(), DEFAULT_ONTOLOGY)
    p = x._prompt("2023-05-20T00:00:00", [(0, "user", "hi")], [])
    assert "WITH WHOM" in p and "companion" in p and "Never guess a unit" in p
