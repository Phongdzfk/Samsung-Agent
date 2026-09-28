"""Năm công cụ của agent đọc (APEX-MEM §4 + PropertySearch do nhóm thiết kế).

Mọi công cụ trả văn bản markdown cho LLM đọc, đồng thời ghi lại các phiên hội thoại mà kết quả
đã chạm tới (seen_sessions) → đo được "công cụ có tìm ra phiên bằng chứng hay không".
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable

from ..store.graphdb import GRAPHSQL_TABLES, GraphDB, ReadOnlySQLError
from ..store.search import hybrid_search
from ..store.vector import VectorIndex
from ..util import md_table, truncate


@dataclass
class ToolContext:
    db: GraphDB
    index: VectorIndex
    question_date: str | None = None
    search_k: int = 10
    max_chars: int = 6000
    seen_sessions: set[str] = field(default_factory=set)
    sql_errors: int = 0


def _val(value_json: str) -> str:
    v = json.loads(value_json)
    return ", ".join(map(str, v)) if isinstance(v, list) else str(v)


def _sessions_of_facts(db: GraphDB, fact_ids: list[int]) -> dict[int, tuple[str, str]]:
    if not fact_ids:
        return {}
    ph = ",".join("?" * len(fact_ids))
    rows = db.conn.execute(
        f"SELECT ev.fact_id, t.session_id, t.session_date FROM evidence ev "
        f"JOIN turns t ON t.turn_id = ev.turn_id WHERE ev.fact_id IN ({ph})", fact_ids)
    return {r["fact_id"]: (r["session_id"], r["session_date"]) for r in rows}


# ---------------------------------------------------------------- SchemaViewer

SCHEMA_DOC = """# Memory graph (SQLite, READ-ONLY). Tables you may query with graph_sql:
- turns(turn_id, session_id, turn_index, speaker['user'|'assistant'], text, session_date)
    raw conversation turns; session_date = when that conversation took place
- entities(entity_id, name, type, role, aliases_json)
    people/places/things. The user is name='User' (role 'Speaker'); the assistant is name='Assistant'
- properties(property_id, name, dtype)   attribute names in snake_case
- events(event_id, type, anchor_datetime, location, session_id)   something that happened, with a time
- event_participants(event_id, entity_id)
- facts(fact_id, subject_id -> entities, property_id -> properties, value_json, dtype, t_from, t_to,
        confidence, event_id -> events, created_at)
- evidence(evidence_id, fact_id, event_id, turn_id -> turns, span)   links each fact to its source turn"""

GUIDE = """## How memory works
- APPEND-ONLY: nothing is overwritten. One property can have several values over time.
  Effective time of a fact = COALESCE(facts.t_from, events.anchor_datetime).
  Current value = the one with the latest effective time (<= the question date). Older rows are history,
  useful for "before/previously/how did it change" questions.
- value_json is JSON: strings are quoted. Use json_extract(f.value_json,'$') to get the raw value.
- Dates are ISO 8601; use julianday()/date() for arithmetic and ordering.
- Extraction is imperfect: if facts look incomplete, read the raw turns (search tool or SQL on turns).
## Tool strategy
- entity_lookup: current + historical values for an entity (best for "what is my current X").
- search: free-text hybrid search over facts, entities and raw turns (use first when unsure).
- property_search: find exact property names before filtering on them in SQL.
- graph_sql: counting, aggregation across sessions, ordering by time, date differences."""

EXAMPLES = """## SQL examples
-- history of one property of the user, newest first
SELECT p.name, json_extract(f.value_json,'$') AS value,
       COALESCE(f.t_from, e.anchor_datetime) AS effective, e.session_id
FROM facts f JOIN properties p ON p.property_id=f.property_id
JOIN events e ON e.event_id=f.event_id JOIN entities s ON s.entity_id=f.subject_id
WHERE s.name='User' AND p.name='japanese_level' ORDER BY effective DESC;
-- days between two events
SELECT julianday(b.anchor_datetime) - julianday(a.anchor_datetime) AS days
FROM events a, events b WHERE a.event_id=12 AND b.event_id=40;
-- count distinct things across sessions (e.g. items bought)
SELECT COUNT(DISTINCT json_extract(f.value_json,'$')) FROM facts f
JOIN properties p ON p.property_id=f.property_id WHERE p.name LIKE '%purchase%';
-- raw turns of a session in order
SELECT turn_index, speaker, text FROM turns WHERE session_id='s1' ORDER BY turn_index;"""


def schema_viewer(ctx: ToolContext, include_examples: bool = True,
                  include_guide: bool = True) -> str:
    db = ctx.db
    c = db.counts()
    props = db.conn.execute(
        "SELECT p.name, p.dtype, COUNT(f.fact_id) n FROM properties p "
        "LEFT JOIN facts f ON f.property_id=p.property_id GROUP BY p.property_id "
        "ORDER BY n DESC LIMIT 60").fetchall()
    types = db.conn.execute("SELECT type, COUNT(*) n FROM entities GROUP BY type "
                            "ORDER BY n DESC LIMIT 20").fetchall()
    span = db.conn.execute("SELECT MIN(session_date), MAX(session_date), "
                           "COUNT(DISTINCT session_id) FROM turns").fetchone()
    parts = [SCHEMA_DOC,
             f"\n## Stats\n{c}\nconversations: {span[2]} sessions from {span[0]} to {span[1]}"
             + (f"\nQUESTION DATE (now): {ctx.question_date}" if ctx.question_date else ""),
             "entity types: " + ", ".join(f"{r['type']}({r['n']})" for r in types),
             "properties (name:dtype×count): " + ", ".join(
                 f"{r['name']}:{r['dtype']}×{r['n']}" for r in props)]
    if include_guide:
        parts.append(GUIDE)
    if include_examples:
        parts.append(EXAMPLES)
    return "\n".join(parts)


# ---------------------------------------------------------------- EntityLookup

def entity_lookup(ctx: ToolContext, query: str, k: int = 5) -> str:
    db = ctx.db
    hits = hybrid_search(db, ctx.index, "entity", query, k)
    if not hits:
        return "No entities found."
    blocks = []
    for eid, _ in hits:
        r = db.entity(eid)
        aliases = json.loads(r["aliases_json"])
        anchors = db.conn.execute(
            "SELECT COUNT(*), MIN(e.anchor_datetime), MAX(e.anchor_datetime) FROM event_participants ep "
            "JOIN events e ON e.event_id=ep.event_id WHERE ep.entity_id=?", (eid,)).fetchone()
        latest = db.latest_facts(eid)
        rows = db.conn.execute(
            "SELECT f.fact_id, p.name, f.value_json, COALESCE(f.t_from, e.anchor_datetime) AS eff, "
            "f.t_to, e.type AS etype, e.session_id FROM facts f "
            "JOIN properties p ON p.property_id=f.property_id JOIN events e ON e.event_id=f.event_id "
            "WHERE f.subject_id=? ORDER BY julianday(eff) DESC, f.fact_id DESC LIMIT 25",
            (eid,)).fetchall()
        ctx.seen_sessions.update(s for s, _ in _sessions_of_facts(
            db, [f.fact_id for f in latest] + [x["fact_id"] for x in rows]).values())
        head = (f"## Entity #{eid} · {r['name']} ({r['type']})"
                + (f" · aliases: {', '.join(aliases)}" if aliases else "")
                + f"\nevents: {anchors[0]} (first {anchors[1]}, last {anchors[2]})")
        lt = md_table(["property", "latest value", "effective", "fact_id"],
                      [(f.property_name, _val(json.dumps(f.value)), f.t_from or f.anchor_datetime,
                        f.fact_id) for f in latest[:30]])
        hist = md_table(["property", "value", "effective", "t_to", "event", "session", "fact_id"],
                        [(x["name"], _val(x["value_json"]), x["eff"], x["t_to"], x["etype"],
                          x["session_id"], x["fact_id"]) for x in rows])
        blocks.append(f"{head}\n### latest\n{lt}\n### history (newest first)\n{hist}")
    return truncate("\n\n".join(blocks), ctx.max_chars)


# ---------------------------------------------------------------- GraphSQL

def graph_sql(ctx: ToolContext, sql: str) -> str:
    try:
        out = ctx.db.run_readonly_sql(sql, max_rows=100)
    except ReadOnlySQLError as e:
        ctx.sql_errors += 1
        return (f"SQL ERROR ({e.reason}): {e}. Only one SELECT/WITH statement over tables "
                f"{sorted(GRAPHSQL_TABLES)} is allowed. Call schema_viewer for columns.")
    if "session_id" in out["columns"]:
        i = out["columns"].index("session_id")
        ctx.seen_sessions.update(str(r[i]) for r in out["rows"] if r[i])
    if not out["rows"]:
        return "(0 rows)"
    table = md_table(out["columns"], out["rows"], cell_max=400)
    note = "\n(truncated to 100 rows)" if out["truncated"] else f"\n({len(out['rows'])} rows)"
    return truncate(table + note, ctx.max_chars)


# ---------------------------------------------------------------- Search

def search(ctx: ToolContext, query: str, k: int | None = None) -> str:
    db, k = ctx.db, k or ctx.search_k
    fact_hits = [i for i, _ in hybrid_search(db, ctx.index, "fact", query, k)]
    turn_hits = [i for i, _ in hybrid_search(db, ctx.index, "turn", query, k)]
    ent_hits = [i for i, _ in hybrid_search(db, ctx.index, "entity", query, 5)]
    prop_hits = [i for i, _ in ctx.index.query("property", query, 5)]
    parts = []
    if fact_hits:
        facts = db.get_facts_by_ids(fact_hits)
        where = _sessions_of_facts(db, fact_hits)
        ctx.seen_sessions.update(s for s, _ in where.values())
        rows = []
        for f in facts:
            subj = db.entity(f.subject_id)["name"]
            ev = db.conn.execute("SELECT type, location FROM events WHERE event_id=?",
                                 (f.event_id,)).fetchone()
            sid, sdate = where.get(f.fact_id, ("", ""))
            rows.append((f.fact_id, subj, f.property_name, _val(json.dumps(f.value)),
                         f.t_from or f.anchor_datetime, f.t_to,
                         ev["type"] + (f"@{ev['location']}" if ev["location"] else ""), sid, sdate))
        parts.append("## Facts\n" + md_table(
            ["fact_id", "subject", "property", "value", "effective", "t_to", "event", "session",
             "session_date"], rows))
    if turn_hits:
        ph = ",".join("?" * len(turn_hits))
        by_id = {r["turn_id"]: r for r in db.conn.execute(
            f"SELECT * FROM turns WHERE turn_id IN ({ph})", turn_hits)}
        lines = []
        for tid in turn_hits:
            r = by_id.get(tid)
            if r is None:
                continue
            ctx.seen_sessions.add(r["session_id"])
            lines.append(f"[turn {tid} · session {r['session_id']} #{r['turn_index']} · "
                         f"{r['session_date']} · {r['speaker']}] {truncate(r['text'], 600)}")
        parts.append("## Conversation turns\n" + "\n".join(lines))
    if ent_hits:
        parts.append("## Entities: " + "; ".join(
            f"#{e} {db.entity(e)['name']} ({db.entity(e)['type']})" for e in ent_hits))
    if prop_hits:
        names = [db.conn.execute("SELECT name FROM properties WHERE property_id=?", (p,)).fetchone()[0]
                 for p in prop_hits]
        parts.append("## Properties: " + ", ".join(names))
    return truncate("\n\n".join(parts) or "No results.", ctx.max_chars)


# ---------------------------------------------------------------- PropertySearch

def property_search(ctx: ToolContext, query: str, k: int = 10) -> str:
    db = ctx.db
    dense = [i for i, _ in ctx.index.query("property", query, k)]
    words = [w for w in query.lower().replace("_", " ").split() if len(w) > 2]
    lex = []
    for w in words[:5]:
        lex += [r[0] for r in db.conn.execute(
            "SELECT property_id FROM properties WHERE name LIKE ?", (f"%{w}%",))]
    ids = list(dict.fromkeys(dense + lex))[:k]
    if not ids:
        return "No properties found."
    rows = []
    for pid in ids:
        p = db.conn.execute("SELECT name, dtype FROM properties WHERE property_id=?", (pid,)).fetchone()
        stats = db.conn.execute(
            "SELECT COUNT(*) n, GROUP_CONCAT(DISTINCT s.name) subj FROM facts f "
            "JOIN entities s ON s.entity_id=f.subject_id WHERE f.property_id=?", (pid,)).fetchone()
        ex = [_val(r[0]) for r in db.conn.execute(
            "SELECT value_json FROM facts WHERE property_id=? ORDER BY fact_id DESC LIMIT 3", (pid,))]
        rows.append((p["name"], p["dtype"], stats["n"], truncate(stats["subj"] or "", 80),
                     "; ".join(ex)))
    return md_table(["property", "dtype", "#facts", "subjects", "example values"], rows)


# ---------------------------------------------------------------- đăng ký

TOOL_SPECS: dict[str, dict] = {
    "schema_viewer": {
        "description": "Show the memory database schema, statistics, property names, usage guide and "
                       "SQL examples. Call this first when planning.",
        "parameters": {"type": "object", "properties": {
            "include_examples": {"type": "boolean", "default": True},
            "include_guide": {"type": "boolean", "default": True}}, "required": []}},
    "entity_lookup": {
        "description": "Find entities (people, places, things, the User) by name/description and "
                       "show their latest property values plus full value history with times.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}, "k": {"type": "integer", "default": 5}},
            "required": ["query"]}},
    "graph_sql": {
        "description": "Run ONE read-only SQLite SELECT (or WITH) statement over the memory graph "
                       "tables. Use for counting, aggregation, ordering by time and date arithmetic.",
        "parameters": {"type": "object", "properties": {"sql": {"type": "string"}},
                       "required": ["sql"]}},
    "search": {
        "description": "Hybrid (semantic + keyword) search over facts, entities, properties and the "
                       "raw conversation turns. Returns matching facts with times and source "
                       "sessions, plus the original turns.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}, "k": {"type": "integer", "default": 10}},
            "required": ["query"]}},
    "property_search": {
        "description": "Find exact property (attribute) names matching a description, with counts, "
                       "subjects and example values. Use before filtering by property in SQL.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"}, "k": {"type": "integer", "default": 10}},
            "required": ["query"]}},
}

TOOL_FUNCS: dict[str, Callable[..., str]] = {
    "schema_viewer": schema_viewer, "entity_lookup": entity_lookup, "graph_sql": graph_sql,
    "search": search, "property_search": property_search,
}


def openai_tools(names: list[str]) -> list[dict]:
    return [{"type": "function", "function": {"name": n, **TOOL_SPECS[n]}} for n in names]


def run_tool(ctx: ToolContext, name: str, args: dict[str, Any], allowed: list[str]) -> str:
    if name not in allowed:
        return f"ERROR: unknown tool '{name}'. Available: {', '.join(allowed)}"
    params = TOOL_SPECS[name]["parameters"]["properties"]
    clean = {k: v for k, v in (args or {}).items() if k in params}
    missing = [r for r in TOOL_SPECS[name]["parameters"]["required"] if r not in clean]
    if missing:
        return f"ERROR: missing argument(s) {missing} for {name}"
    try:
        return TOOL_FUNCS[name](ctx, **clean)
    except Exception as e:                     # công cụ không được làm sập vòng lặp agent
        return f"ERROR in {name}: {type(e).__name__}: {e}"
