"""Baseline SimpleSearch của LongMemEval: khóa = giá trị + fact (K = V + fact), lấy top-N phiên,
đưa NGUYÊN VĂN các phiên đó cho LLM đọc rồi trả lời (không agent, không công cụ).

Điểm của một phiên = max(cosine câu hỏi với từng lượt, cosine câu hỏi với từng fact trích từ phiên).
Dùng chung đồ thị đã dựng cho hệ chính → cùng dữ liệu, chỉ khác cách đọc.
"""
from __future__ import annotations

from collections import defaultdict

from ..agent.react import AgentResult
from ..util import Timer, weekday_of
from ..system import MemorySystem

READER_PROMPT = """I will give you several history chats between you and a user{with_facts}.
Please answer the question based on the relevant chat history.
Answer the question step by step: first extract all the relevant information, and then reason
over the information to get the answer. End with a line "FINAL ANSWER: ...". If the history does
not contain the answer, say that the information was not mentioned.

History Chats:

{history}

Current Date: {qdate}
Question: {question}
Answer (step by step):"""


def retrieve_sessions(sys: MemorySystem, question: str, top_n: int,
                      use_facts: bool = True) -> list[tuple[str, float]]:
    db, index = sys.db, sys.index
    q = index.encode_query(question)
    best: dict[str, float] = defaultdict(lambda: -1.0)
    ids, sc = index.all_scores("turn", q)
    if ids:
        sess = {r["turn_id"]: r["session_id"] for r in db.conn.execute(
            "SELECT turn_id, session_id FROM turns")}
        for i, s in zip(ids, sc):
            best[sess[i]] = max(best[sess[i]], float(s))
    ids, sc = index.all_scores("fact", q) if use_facts else ([], [])
    if ids:
        fsess = {r[0]: r[1] for r in db.conn.execute(
            "SELECT ev.fact_id, t.session_id FROM evidence ev JOIN turns t ON t.turn_id=ev.turn_id")}
        for i, s in zip(ids, sc):
            if i in fsess:
                best[fsess[i]] = max(best[fsess[i]], float(s))
    return sorted(best.items(), key=lambda x: -x[1])[:top_n]


def render_session(sys: MemorySystem, session_id: str, max_turn_chars: int = 4000,
                   use_facts: bool = True) -> str:
    db = sys.db
    rows = db.conn.execute("SELECT speaker, text, session_date FROM turns WHERE session_id=? "
                           "ORDER BY turn_index", (session_id,)).fetchall()
    facts = db.conn.execute(
        "SELECT DISTINCT s.name, p.name, f.value_json FROM facts f "
        "JOIN evidence ev ON ev.fact_id=f.fact_id JOIN turns t ON t.turn_id=ev.turn_id "
        "JOIN entities s ON s.entity_id=f.subject_id JOIN properties p ON p.property_id=f.property_id "
        "WHERE t.session_id=?", (session_id,)).fetchall()
    date = rows[0]["session_date"] if rows else ""
    body = "\n".join(f"{r['speaker']}: {r['text'][:max_turn_chars]}" for r in rows)
    fx = "\n".join(f"- {a}.{b} = {c}" for a, b, c in facts) if use_facts else ""
    return f"### Session date: {date}\n{body}" + (f"\nExtracted facts:\n{fx}" if fx else "")


def simple_search_answer(sys: MemorySystem, question: str, question_date: str | None,
                         top_n: int = 5, salt: str = "", llm=None,
                         use_facts: bool = True) -> AgentResult:
    """use_facts=True: K = V + fact (baseline của LongMemEval). False: K = V, RAG thường."""
    llm = llm or sys.llm
    t = Timer()
    with t:
        top = retrieve_sessions(sys, question, top_n, use_facts)
        dates = {sid: sys.db.conn.execute("SELECT session_date FROM turns WHERE session_id=? LIMIT 1",
                                          (sid,)).fetchone()[0] for sid, _ in top}
        ordered = sorted((sid for sid, _ in top), key=lambda s: dates[s])
        history = "\n\n".join(render_session(sys, sid, use_facts=use_facts) for sid in ordered)
        qd = f"{(question_date or '')[:16].replace('T', ' ')} ({weekday_of(question_date)})" \
            if question_date else "unknown"
        with_facts = ", with facts extracted from each chat" if use_facts else ""
        text = llm.complete_text(READER_PROMPT.format(history=history, qdate=qd,
                                                      question=question, with_facts=with_facts),
                                     role="reader", salt=salt)
    # Đưa TOÀN BỘ đầu ra (cả phần suy luận) cho judge, như cách chấm của LongMemEval:
    # cắt chỉ lấy dòng FINAL ANSWER làm baseline bị thiệt ở câu preference.
    answer = text.strip()
    return AgentResult(answer=answer, steps=[{"tool": "simple_search",
                                              "args": {"top_sessions": ordered},
                                              "output": text[:3000], "ms": round(t.ms)}],
                       n_llm_calls=1, seen_sessions=ordered, ms=t.ms)
