"""Test đầu–cuối offline: luồng ghi, công cụ, agent, baseline. Không gọi mạng, không tốn hạn mức."""
import json

import pytest

from ltm.agent.react import ReActAgent
from ltm.agent.tools import (entity_lookup, graph_sql, property_search, run_tool, schema_viewer,
                             search)
from ltm.baselines.simple_search import simple_search_answer
from ltm.memory.relevance import Session, filter_sessions
from ltm.system import MemorySystem

from fakes import make_cfg, make_embedder, make_llm

S1 = Session("s1", "2023-03-10T10:00:00", [
    {"role": "user", "content": "I just passed JLPT N5! Planning a trip to Tokyo next year."},
    {"role": "assistant", "content": "Congrats! For Tokyo I recommend Ichiran, Afuri, Tsuta."}])
S2 = Session("s2", "2024-01-22T09:00:00", [
    {"role": "user", "content": "Good news, I'm N4 now."},
    {"role": "assistant", "content": "Great progress!"}])
NOISE = Session("s0", "2022-12-01T08:00:00", [
    {"role": "user", "content": "What is a good recipe for pancakes?"},
    {"role": "assistant", "content": "Mix flour, eggs and milk."}])


@pytest.fixture
def sysm(tmp_path):
    s = MemorySystem(make_cfg(tmp_path), tmp_path / "g.db", make_llm(), make_embedder())
    s.builder.build_haystack([S2, S1, NOISE], {"s1", "s2"}, store_all_turns=True)
    yield s
    s.close()


def test_append_only_keeps_both_versions_and_latest_wins(sysm):
    db = sysm.db
    user = db.conn.execute("SELECT entity_id FROM entities WHERE name='User'").fetchone()[0]
    prop = db.property_by_name("japanese_level")["property_id"]
    hist = [f.value for f in db.fact_history(user, prop)]
    assert hist == ["N5", "N4"]                                   # dựng theo thứ tự thời gian
    assert [f.value for f in db.latest_facts(user, prop)] == ["N4"]
    assert [f.value for f in db.latest_facts(user, prop, as_of="2023-12-31")] == ["N5"]


def test_every_fact_has_evidence_turn_in_right_session(sysm):
    rows = sysm.db.conn.execute(
        "SELECT json_extract(f.value_json,'$'), t.session_id FROM facts f "
        "JOIN evidence ev ON ev.fact_id=f.fact_id JOIN turns t ON t.turn_id=ev.turn_id "
        "JOIN properties p ON p.property_id=f.property_id WHERE p.name='japanese_level'").fetchall()
    assert sorted(map(tuple, rows)) == [("N4", "s2"), ("N5", "s1")]


def test_filtered_session_stored_as_turns_but_not_extracted(sysm):
    db = sysm.db
    assert db.has_session("s0")
    n = db.conn.execute("SELECT COUNT(*) FROM events WHERE session_id='s0'").fetchone()[0]
    assert n == 0


def test_speakers_are_fixed_entities_and_places_created(sysm):
    names = {r["name"]: r for r in sysm.db.all_entities()}
    assert names["User"]["role"] == "Speaker" and names["Assistant"]["role"] == "Agent"
    assert names["Tokyo"]["type"] == "Place"
    assert sum(1 for n in names if n == "User") == 1


def test_assistant_recommendations_stored_as_list(sysm):
    v = sysm.db.conn.execute(
        "SELECT value_json FROM facts f JOIN properties p ON p.property_id=f.property_id "
        "WHERE p.name='recommended_items'").fetchone()[0]
    assert json.loads(v) == ["Ichiran", "Afuri", "Tsuta"]


def test_build_is_idempotent(sysm):
    before = sysm.db.counts()
    sysm.builder.build_haystack([S1, S2, NOISE], {"s1", "s2"})
    assert sysm.db.counts() == before


def test_ingest_trace_logged_with_rejections(sysm):
    rows = sysm.db.conn.execute("SELECT payload_json FROM trace WHERE kind='ingest'").fetchall()
    assert len(rows) == 2
    assert all("resolve" in json.loads(r[0]) for r in rows)


def test_vector_index_is_derived(sysm):
    counts = sysm.index.rebuild()
    assert counts["turn"] == sysm.db.counts()["turns"]
    assert counts["fact"] == sysm.db.counts()["facts"]


# ---------------------------------------------------------------- công cụ

def test_schema_viewer_lists_tables_and_properties(sysm):
    out = schema_viewer(sysm.tool_context("2024-02-01T00:00:00"))
    for t in ("turns", "entities", "facts", "evidence", "japanese_level", "QUESTION DATE"):
        assert t in out


def test_entity_lookup_shows_latest_and_history(sysm):
    ctx = sysm.tool_context("2024-02-01T00:00:00")
    out = entity_lookup(ctx, "User", 1)
    assert "| japanese_level | N4 |" in out and "N5" in out
    assert {"s1", "s2"} <= ctx.seen_sessions


def test_graph_sql_reads_and_blocks_writes(sysm):
    ctx = sysm.tool_context(None)
    out = graph_sql(ctx, "SELECT session_id, COUNT(*) n FROM turns GROUP BY session_id")
    assert "s1" in out and "(3 rows)" in out
    assert "s0" in ctx.seen_sessions
    bad = graph_sql(ctx, "DELETE FROM facts")
    assert bad.startswith("SQL ERROR") and ctx.sql_errors == 1
    assert "SQL ERROR" in graph_sql(ctx, "SELECT * FROM trace")


def test_search_returns_facts_and_turns(sysm):
    ctx = sysm.tool_context(None)
    out = search(ctx, "N4 japanese level")
    assert "## Facts" in out and "## Conversation turns" in out and "N4" in out
    assert "s2" in ctx.seen_sessions


def test_property_search_finds_exact_name(sysm):
    assert "japanese_level" in property_search(sysm.tool_context(None), "japanese")


def test_run_tool_rejects_unknown_and_bad_args(sysm):
    ctx = sysm.tool_context(None)
    assert run_tool(ctx, "drop_db", {}, ["search"]).startswith("ERROR")
    assert "missing" in run_tool(ctx, "search", {}, ["search"])
    assert run_tool(ctx, "search", {"query": "Tokyo", "bogus": 1}, ["search"])


# ---------------------------------------------------------------- agent

def test_agent_function_calling_answers_latest(sysm):
    res = sysm.answer("What is my current Japanese level?", "2024-02-01T00:00:00")
    assert res.answer == "N4"
    assert [s["tool"] for s in res.steps] == ["entity_lookup"]
    assert res.n_llm_calls == 2 and not res.forced


def test_agent_forced_answer_after_max_steps(sysm):
    loop = lambda m, t: ({"content": None, "tool_calls": [{"name": "search",
                                                          "arguments": {"query": "x"}}]}
                         if t else {"content": "gave up"})
    agent = ReActAgent(make_llm(agent=loop), ["search"], max_steps=3)
    res = agent.run("q?", sysm.tool_context(None))
    assert res.forced and res.answer == "gave up" and len(res.steps) == 3


def test_agent_json_protocol(sysm):
    script = [json.dumps({"thought": "look", "action": "entity_lookup", "args": {"query": "User"}}),
              "not json at all",
              json.dumps({"thought": "done", "action": "answer", "answer": "N4"})]
    agent = ReActAgent(make_llm(agent=script), ["entity_lookup"], protocol="json")
    res = agent.run("level?", sysm.tool_context(None))
    assert res.answer == "N4" and res.steps[0]["tool"] == "entity_lookup"


def test_simple_search_baseline(sysm):
    res = simple_search_answer(sysm, "What is my Japanese level now?", "2024-02-01T00:00:00", 2)
    assert "N4" in res.answer and len(res.seen_sessions) == 2   # judge nhận TOÀN BỘ đầu ra


def test_simple_search_kv_ignores_facts(sysm):
    from ltm.baselines.simple_search import render_session
    assert "Extracted facts" in render_session(sysm, "s2")
    assert "Extracted facts" not in render_session(sysm, "s2", use_facts=False)
    res = simple_search_answer(sysm, "What is my Japanese level now?", "2024-02-01T00:00:00", 2,
                               use_facts=False)
    assert len(res.seen_sessions) == 2


def test_agent_prompt_has_date_anchors_and_rules():
    from ltm.agent.react import ReActAgent, date_anchors
    a = ReActAgent(make_llm(), ["search"])
    p = a.system_prompt("2023-03-11T05:28:00")
    assert "2 months ago = 2023-01-11" in p and "1 week ago = 2023-03-04" in p
    assert "Who said it matters" in p and 'start with "Yes" or "No"' in p
    assert "1 month ago = 2024-02-29" in date_anchors("2024-03-31T10:00:00")   # cuối tháng nhuận


def test_chat_prompt_still_formats():
    from ltm.agent.react import ReActAgent
    from ltm.demo.chat import CHAT_SYSTEM
    p = ReActAgent(make_llm(), ["search"], system_template=CHAT_SYSTEM).system_prompt(
        "2024-05-01T09:00:00")
    assert "Reference dates" in p and "{" not in p.split("Reference dates")[0]


# ---------------------------------------------------------------- lọc phiên

def test_relevance_filter_keeps_matching_sessions():
    fr = filter_sessions("What JLPT level N4 did I reach?", [NOISE, S1, S2], make_embedder(), 2)
    assert {s.session_id for s in fr.kept} == {"s1", "s2"}
    assert [s.session_id for s in fr.kept] == ["s1", "s2"]          # theo thời gian


# ---------------------------------------------------------------- chat

def test_chat_incremental_ingest(tmp_path):
    s = MemorySystem(make_cfg(tmp_path), tmp_path / "c.db", make_llm(), make_embedder())
    s.builder.ingest_turns("chat-1", "2024-05-01T09:00:00", [(0, "user", "I am N3 now"),
                                                             (1, "assistant", "Nice")])
    s.builder.ingest_turns("chat-1", "2024-05-01T09:05:00", [(2, "user", "Actually N2"),
                                                             (3, "assistant", "Wow")])
    user = s.db.conn.execute("SELECT entity_id FROM entities WHERE name='User'").fetchone()[0]
    assert [f.value for f in s.db.latest_facts(user)] == ["N2"]
    s.close()


def test_threshold_filter_respects_min_and_max():
    from ltm.memory.relevance import FilterResult, select
    fr = FilterResult([], [("a", 3), ("b", 2), ("c", 1), ("d", 0.5)],
                      {"a": 0.2, "b": 0.7, "c": 0.9, "d": 0.1})
    assert select(fr, "threshold", threshold=0.6, min_sessions=1, max_sessions=10) == {"b", "c"}
    # dưới tối thiểu → lấp bằng phiên hạng RRF cao nhất dưới ngưỡng
    assert select(fr, "threshold", threshold=0.8, min_sessions=2, max_sessions=10) == {"a", "c"}
    # vượt tối đa → giữ phiên hạng RRF cao
    assert select(fr, "threshold", threshold=0.0, min_sessions=1, max_sessions=2) == {"a", "b"}
    assert select(fr, "topk", top_sessions=3) == {"a", "b", "c"}
    assert select(fr, "all") == {"a", "b", "c", "d"}


def test_filter_threshold_mode_end_to_end():
    fr = filter_sessions("What JLPT level N4 did I reach?", [NOISE, S1, S2], make_embedder(),
                         mode="threshold", threshold=0.99, min_sessions=2, max_sessions=5)
    assert len(fr.kept) == 2
