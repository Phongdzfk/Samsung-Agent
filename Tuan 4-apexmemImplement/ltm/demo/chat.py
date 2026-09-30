"""Trợ lý có bộ nhớ dài hạn — demo trò chuyện trực tiếp.

    python -m ltm.demo.chat --db data/chat/demo.db
Bộ nhớ nằm trong file .db: tắt đi mở lại vẫn nhớ. Lệnh trong phiên:
    /date 2024-05-01   giả lập "hôm nay" là ngày khác (để demo cập nhật kiến thức theo thời gian)
    /me                xem mọi điều đã nhớ về User (giá trị mới nhất + lịch sử)
    /search <câu>      chạy công cụ Search      /sql <SELECT ...>  chạy GraphSQL
    /stats             số bản ghi                /trace             bật/tắt in các bước agent
    /quit
"""
from __future__ import annotations

import argparse
from datetime import datetime

from ..adapters.embed import build_embedder
from ..adapters.llm import build_llm
from ..agent.tools import entity_lookup, graph_sql, search
from ..config import load_config, resolve_path
from ..system import MemorySystem

CHAT_SYSTEM = """You are a helpful personal assistant with long-term memory of all past
conversations with this user, accessible through tools.
Current date: {qdate} ({weekday}).
{anchors}- If the message may depend on anything the user told you before (their life, preferences, plans,
  people, past events, things you recommended), look it up with the tools BEFORE answering.
- For small talk or general knowledge, answer directly without tools.
- Facts can change over time: prefer the most recent value and mention the change when useful.
- Never invent memories. If nothing is stored, say you don't remember it.
- Reply in the same language the user writes in."""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/chat/demo.db")
    ap.add_argument("--config-file", default=None)
    a = ap.parse_args()
    cfg = load_config(a.config_file)
    llm = build_llm(cfg.llm)
    sysm = MemorySystem(cfg, resolve_path(a.db), llm, build_embedder(cfg.embed))
    agent = sysm.agent(system_template=CHAT_SYSTEM)
    fake_date: str | None = None
    session_id = "chat-" + datetime.now().strftime("%Y%m%d-%H%M%S")
    turn_i, recent, show_trace = 0, [], True
    print(f"Bộ nhớ: {a.db} · {sysm.db.counts()} · gõ /quit để thoát")
    while True:
        try:
            msg = input("\nBạn> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not msg:
            continue
        now = fake_date or datetime.now().replace(microsecond=0).isoformat()
        ctx = sysm.tool_context(now)
        if msg in ("/quit", "/exit"):
            break
        if msg.startswith("/date"):
            d = msg[5:].strip()
            fake_date = (d + "T09:00:00") if len(d) == 10 else (d or None)
            session_id = f"chat-{(fake_date or 'now')[:10]}-{datetime.now():%H%M%S}"
            turn_i, recent = 0, []
            print(f"(ngày hiện tại = {fake_date or 'thật'}; bắt đầu phiên mới {session_id})")
            continue
        if msg == "/me":
            print(entity_lookup(ctx, "User", 1))
            continue
        if msg.startswith("/search "):
            print(search(ctx, msg[8:]))
            continue
        if msg.startswith("/sql "):
            print(graph_sql(ctx, msg[5:]))
            continue
        if msg == "/stats":
            print(sysm.db.counts())
            continue
        if msg == "/trace":
            show_trace = not show_trace
            print(f"in các bước agent: {show_trace}")
            continue

        res = agent.run(msg, ctx, history=recent[-6:])
        if show_trace:
            for st in res.steps:
                print(f"  · {st['tool']}({str(st['args'])[:100]})  {st['ms']}ms")
        answer = res.answer or f"(lỗi: {res.error})"
        print(f"\nTrợ lý> {answer}")
        recent += [{"role": "user", "content": msg}, {"role": "assistant", "content": answer}]
        stats = sysm.builder.ingest_turns(session_id, now, [(turn_i, "user", msg),
                                                            (turn_i + 1, "assistant", answer)])
        turn_i += 2
        if show_trace:
            print(f"  (đã ghi nhớ: {stats['facts']} fact, {stats['events']} sự kiện)")
    sysm.close()


if __name__ == "__main__":
    main()
