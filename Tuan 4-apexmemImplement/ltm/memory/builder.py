"""Luồng ghi đầy đủ: lượt gốc → trích xuất → giải quyết → ghi append-only + cập nhật chỉ mục."""
from __future__ import annotations

from collections import Counter
from typing import Iterable

from ..store.graphdb import GraphDB, ValidationError
from ..store.vector import VectorIndex, property_text
from ..util import Timer, normalize_name
from .extractor import FactExtractor, coerce_value, Rejected
from .relevance import Session
from .resolver import Resolver


class GraphBuilder:
    def __init__(self, db: GraphDB, index: VectorIndex, extractor: FactExtractor,
                 resolver: Resolver):
        self.db, self.index, self.extractor, self.resolver = db, index, extractor, resolver

    # ---- lượt gốc (không gọi LLM)
    def add_session_turns(self, s: Session) -> dict[int, int]:
        if self.db.has_session(s.session_id):
            return {r["turn_index"]: r["turn_id"] for r in self.db.conn.execute(
                "SELECT turn_index, turn_id FROM turns WHERE session_id=?", (s.session_id,))}
        rows = [(s.session_id, i, t["role"] if t["role"] in ("user", "assistant") else "user",
                 t["content"], s.date) for i, t in enumerate(s.turns) if t.get("content")]
        idx = [r[1] for r in rows]
        ids = self.db.add_turns(rows)
        self.index.upsert("turn", [(tid, r[3]) for tid, r in zip(ids, rows)])
        return dict(zip(idx, ids))

    # ---- một phiên
    def build_session(self, s: Session) -> dict:
        turn_ids = self.add_session_turns(s)
        turns = [(i, t["role"], t["content"]) for i, t in enumerate(s.turns) if i in turn_ids]
        stats = self._extract_and_write(s.session_id, s.date, turns, turn_ids)
        self.db.set_meta(f"built:{s.session_id}", True)
        return stats

    def ingest_turns(self, session_id: str, date: str, turns: list[tuple[int, str, str]]) -> dict:
        """Nạp lượt MỚI vào một phiên đang diễn ra (chế độ chat): lưu, nhúng, trích, ghi."""
        rows = [(session_id, i, sp, tx, date) for i, sp, tx in turns]
        ids = self.db.add_turns(rows)
        self.index.upsert("turn", [(tid, r[3]) for tid, r in zip(ids, rows)])
        return self._extract_and_write(session_id, date, turns,
                                       {i: tid for (i, _, _), tid in zip(turns, ids)})

    def _extract_and_write(self, session_id, date, turns, turn_ids) -> dict:
        timer = Timer()
        with timer:
            turns = [t for t in turns if self.extractor.include_assistant or t[1] == "user"]
            events, rejected, xstats = self.extractor.extract_session(date, turns)
            res = self.resolver.resolve(events)
            written = self._write(session_id, events, res, turn_ids, rejected)
        stats = {"session_id": session_id, "turns": len(turns), "events": written["events"],
                 "facts": written["facts"], "extract": xstats, "resolve": res.stats,
                 "rejected": dict(Counter(r["reason"] for r in rejected)), "ms": round(timer.ms)}
        self.db.log_trace("ingest", stats | {"resolution_decisions": res.decisions[:50]})
        return stats

    def _write(self, session_id, events, res, turn_ids, rejected) -> dict:
        new_props: list[tuple[int, str]] = []
        new_facts: list[int] = []
        n_events = 0
        for ev in events:
            subj_ids = {res.entity_of.get(normalize_name(f.subject)) for f in ev.facts}
            part_ids = {res.entity_of.get(normalize_name(n)) for n, _, _ in ev.participants}
            participants = [i for i in (subj_ids | part_ids) if i is not None]
            facts_ok = [f for f in ev.facts if res.entity_of.get(normalize_name(f.subject))]
            for f in ev.facts:
                if f not in facts_ok:
                    rejected.append({"reason": "subject_unresolved", "detail": f.subject})
            if not facts_ok and not participants:
                continue
            eid = self.db.add_event(ev.type, ev.anchor_datetime, location=ev.location,
                                    session_id=session_id, participants=participants)
            n_events += 1
            for f in facts_ok:
                try:
                    fid, created = self._write_fact(f, eid, res, turn_ids)
                    new_facts.append(fid)
                    if created:
                        new_props.append(created)
                except (ValidationError, Rejected) as e:
                    rejected.append({"reason": e.reason, "detail": str(e)[:120],
                                     "property": f.property})
        if new_props:
            self.index.upsert("property", new_props)
        if new_facts:
            ph = ",".join("?" * len(new_facts))
            self.index.upsert("fact", [(r["rowid"], r["content"]) for r in self.db.conn.execute(
                f"SELECT rowid, content FROM facts_fts WHERE rowid IN ({ph})", new_facts)])
        return {"events": n_events, "facts": len(new_facts)}

    def _write_fact(self, f, event_id, res, turn_ids):
        name = res.property_of.get(f.property, f.property)
        value, dtype = f.value, f.dtype
        existing = self.db.property_by_name(name)
        created = None
        if existing is not None and existing["dtype"] != dtype:
            value2, dtype2 = coerce_value(value, existing["dtype"])
            if dtype2 == existing["dtype"]:
                value, dtype = value2, dtype2
            elif existing["dtype"] in ("str", "enum"):
                value, dtype = str(value), existing["dtype"]
            else:
                raise Rejected("property_dtype_conflict", f"{name}: {existing['dtype']} vs {dtype}")
        if existing is None:
            pid = self.db.add_property(name, dtype)
            created = (pid, property_text(name))
        else:
            pid = existing["property_id"]
        subj = res.entity_of[normalize_name(f.subject)]
        fid = self.db.add_fact(subj, pid, value, event_id=event_id, confidence=f.confidence,
                               evidence=[(turn_ids[f.evidence_turn], f.span)],
                               t_from=f.t_from, t_to=f.t_to)
        return fid, created

    # ---- một câu hỏi LongMemEval: lưu lượt gốc, dựng đồ thị từ các phiên được giữ
    def build_haystack(self, sessions: Iterable[Session], kept_ids: set[str],
                       store_all_turns: bool = True, progress: bool = False) -> dict:
        sessions = sorted(sessions, key=lambda s: s.date)
        per_session = []
        for s in sessions:
            if s.session_id in kept_ids:
                if not self.db.get_meta(f"built:{s.session_id}"):
                    per_session.append(self.build_session(s))
                    if progress:
                        st = per_session[-1]
                        print(f"    dựng {s.session_id}: {st['facts']} fact, {st['ms']} ms",
                              flush=True)
            elif store_all_turns:
                self.add_session_turns(s)
        total = Counter()
        for st in per_session:
            total["facts"] += st["facts"]
            total["events"] += st["events"]
            for k, v in st["rejected"].items():
                total[f"rejected:{k}"] += v
        return {"sessions_built": len(per_session), **total, "counts": self.db.counts()}
