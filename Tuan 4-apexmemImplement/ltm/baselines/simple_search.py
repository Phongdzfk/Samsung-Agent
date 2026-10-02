"""Baseline SimpleSearch của LongMemEval, dạng K = V (RAG thường): lấy top-N phiên theo lượt gốc,
đưa NGUYÊN VĂN các phiên đó cho LLM đọc rồi trả lời (không agent, không công cụ, không fact).

Điểm của một phiên = max cosine giữa câu hỏi và từng lượt của phiên. Không cần dựng đồ thị.
"""
from __future__ import annotations

from collections import defaultdict

from ..agent.react import AgentResult
from ..util import Timer, weekday_of
from ..system import MemorySystem

READER_PROMPT = """I will give you several history chats between you and a user.
Please answer the question based on the relevant chat history.
Answer the question step by step: first extract all the relevant information, and then reason
over the information to get the answer. End with a line "FINAL ANSWER: ...". If the history does
not contain the answer, say that the information was not mentioned.

History Chats:

{history}

Current Date: {qdate}
Question: {question}
Answer (step by step):"""


def retrieve_sessions(sys: MemorySystem, question: str, top_n: int) -> list[tuple[str, float]]:
    db, index = sys.db, sys.index
    q = index.encode_query(question)
    best: dict[str, float] = defaultdict(lambda: -1.0)
    ids, sc = index.all_scores("turn", q)
    if ids:
        sess = {r["turn_id"]: r["session_id"] for r in db.conn.execute(
            "SELECT turn_id, session_id FROM turns")}
        for i, s in zip(ids, sc):
            best[sess[i]] = max(best[sess[i]], float(s))
    return sorted(best.items(), key=lambda x: -x[1])[:top_n]


def render_session(sys: MemorySystem, session_id: str, max_turn_chars: int = 4000) -> str:
    rows = sys.db.conn.execute("SELECT speaker, text, session_date FROM turns WHERE session_id=? "
                               "ORDER BY turn_index", (session_id,)).fetchall()
    date = rows[0]["session_date"] if rows else ""
    body = "\n".join(f"{r['speaker']}: {r['text'][:max_turn_chars]}" for r in rows)
    return f"### Session date: {date}\n{body}"


def simple_search_answer(sys: MemorySystem, question: str, question_date: str | None,
                         top_n: int = 5, salt: str = "", llm=None) -> AgentResult:
    llm = llm or sys.llm
    t = Timer()
    with t:
        top = retrieve_sessions(sys, question, top_n)
        dates = {sid: sys.db.conn.execute("SELECT session_date FROM turns WHERE session_id=? LIMIT 1",
                                          (sid,)).fetchone()[0] for sid, _ in top}
        ordered = sorted((sid for sid, _ in top), key=lambda s: dates[s])
        history = "\n\n".join(render_session(sys, sid) for sid in ordered)
        qd = f"{(question_date or '')[:16].replace('T', ' ')} ({weekday_of(question_date)})" \
            if question_date else "unknown"
        text = llm.complete_text(READER_PROMPT.format(history=history, qdate=qd,
                                                      question=question),
                                     role="reader", salt=salt)
    # Đưa TOÀN BỘ đầu ra (cả phần suy luận) cho judge, như cách chấm của LongMemEval:
    # cắt chỉ lấy dòng FINAL ANSWER làm baseline bị thiệt ở câu preference.
    answer = text.strip()
    return AgentResult(answer=answer, steps=[{"tool": "simple_search",
                                              "args": {"top_sessions": ordered},
                                              "output": text[:3000], "ms": round(t.ms)}],
                       n_llm_calls=1, seen_sessions=ordered, ms=t.ms)
