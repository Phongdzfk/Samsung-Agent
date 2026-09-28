"""Bước 3 luồng ghi — giải quyết thực thể và thuộc tính (APEX-MEM §3.3).

Mỗi nhắc tới thực thể → một trong ba quyết định: choose_existing | propose_new | none.
Để tiết kiệm lời gọi, LLM chỉ được hỏi khi thật sự mơ hồ:
  1. "User"/"Assistant" → thực thể cố định, không hỏi.
  2. Trùng khớp tên/bí danh sau chuẩn hóa → dùng lại, không hỏi.
  3. Không có ứng viên nào đủ gần trong chỉ mục vector → tạo mới, không hỏi.
  4. Còn lại → gom TẤT CẢ nhắc tới mơ hồ của cả đoạn vào MỘT lời gọi LLM.
Thuộc tính làm tương tự: trùng tên → dùng lại; rất gần → gộp; gần vừa → hỏi LLM; xa → tạo mới.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..adapters.llm import BaseLLM, LLMError, LLMFatalError
from ..store.graphdb import ROLES, GraphDB
from ..store.vector import VectorIndex, entity_text, property_text
from ..util import dumps, normalize_name
from .extractor import XEvent

USER_NAMES = {"user", "i", "me", "myself", "the user"}
ASSISTANT_NAMES = {"assistant", "the assistant", "ai", "ai assistant", "chatbot"}


@dataclass
class Resolution:
    entity_of: dict[str, int | None] = field(default_factory=dict)   # normalize_name(mention) -> id
    property_of: dict[str, str] = field(default_factory=dict)        # tên đề xuất -> tên cuối cùng
    stats: dict = field(default_factory=lambda: {
        "mentions": 0, "fixed": 0, "exact": 0, "new_direct": 0, "llm_asked": 0,
        "llm_existing": 0, "llm_new": 0, "llm_none": 0, "prop_reused": 0, "prop_merged": 0,
        "prop_new": 0, "prop_llm": 0, "llm_calls": 0, "llm_failed": 0})
    decisions: list[dict] = field(default_factory=list)


PROMPT = """You resolve new mentions against the entities and properties already stored in a
personal-assistant memory graph.

For each ENTITY mention decide:
- "choose_existing": it refers to one of its candidates (give "id")
- "propose_new": a different real-world entity (give "normalized_name", "type", "aliases")
- "none": not a real entity worth storing (vague pronoun, generic concept)

For each PROPERTY decide whether it means the same attribute as one existing candidate
("use": that exact name) or is a new attribute ("use": null). Same meaning = same attribute of the
same kind of subject (e.g. residence_city ~ home_city; but birth_city != home_city).

ENTITY MENTIONS:
{mentions}

PROPERTIES:
{properties}

Return ONLY JSON:
{{"entities":[{{"mention":"...","decision":"choose_existing|propose_new|none","id":null,
  "normalized_name":"...","type":"...","aliases":[],"confidence":0.9,"reason":"..."}}],
 "properties":[{{"proposed":"...","use":null}}]}}"""


class Resolver:
    def __init__(self, db: GraphDB, index: VectorIndex, llm: BaseLLM, top_k: int = 5,
                 min_candidate_sim: float = 0.60, prop_auto_merge_sim: float = 0.97,
                 prop_candidate_sim: float = 0.80):
        self.db, self.index, self.llm = db, index, llm
        self.top_k, self.min_sim = top_k, min_candidate_sim
        self.prop_auto, self.prop_cand = prop_auto_merge_sim, prop_candidate_sim
        self.user_id = self._fixed("User", "Person", "Speaker")
        self.assistant_id = self._fixed("Assistant", "Software", "Agent")

    def _fixed(self, name: str, type_: str, role: str) -> int:
        row = self.db.conn.execute("SELECT entity_id FROM entities WHERE name=? AND role=?",
                                   (name, role)).fetchone()
        if row:
            return row["entity_id"]
        eid = self.db.add_entity(name, type_, role=role)
        self.index.upsert("entity", [(eid, entity_text(name, type_, []))])
        return eid

    # ---- bảng tra tên chính xác
    def _name_map(self) -> dict[str, list[int]]:
        m: dict[str, list[int]] = {}
        for r in self.db.all_entities():
            for n in [r["name"], *json.loads(r["aliases_json"])]:
                m.setdefault(normalize_name(n), []).append(r["entity_id"])
        return m

    def _new_entity(self, name: str, type_: str, role: str, aliases=()) -> int:
        type_ = type_ if type_ in self.db.ontology else "Other"
        role = role if role in ROLES and role != "Speaker" else "Mentioned"
        eid = self.db.add_entity(name, type_, role=role, aliases=aliases)
        r = self.db.entity(eid)
        self.index.upsert("entity", [(eid, entity_text(name, type_, json.loads(r["aliases_json"])))])
        return eid

    def _alias(self, eid: int, alias: str) -> None:
        r = self.db.entity(eid)
        if normalize_name(alias) == normalize_name(r["name"]):
            return
        self.db.add_alias(eid, alias)
        r = self.db.entity(eid)
        self.index.upsert("entity", [(eid, entity_text(r["name"], r["type"],
                                                       json.loads(r["aliases_json"])))])

    def _entity_card(self, eid: int) -> dict:
        r = self.db.entity(eid)
        facts = self.db.latest_facts(eid)[:6]
        return {"id": eid, "name": r["name"], "type": r["type"],
                "aliases": json.loads(r["aliases_json"])[:5],
                "facts": "; ".join(f"{f.property_name}={f.value}" for f in facts)}

    # ---- chính
    def resolve(self, events: list[XEvent]) -> Resolution:
        res = Resolution()
        st = res.stats
        mentions: dict[str, dict] = {}
        for ev in events:
            for name, type_, role in ev.participants:
                mentions.setdefault(normalize_name(name), {"name": name, "type": type_,
                                                           "role": role, "ctx": []})
            for f in ev.facts:
                m = mentions.setdefault(normalize_name(f.subject), {
                    "name": f.subject, "type": f.subject_type, "role": "Mentioned", "ctx": []})
                if len(m["ctx"]) < 3:
                    m["ctx"].append(f"{f.property}={f.value}" + (f' ("{f.span}")' if f.span else ""))
        st["mentions"] = len(mentions)

        name_map = self._name_map()
        pending: list[tuple[str, dict, list[dict]]] = []
        for key, m in mentions.items():
            if not key:
                res.entity_of[key] = None
            elif key in USER_NAMES:
                res.entity_of[key] = self.user_id
                st["fixed"] += 1
            elif key in ASSISTANT_NAMES:
                res.entity_of[key] = self.assistant_id
                st["fixed"] += 1
            elif key in name_map:
                ids = name_map[key]
                same_type = [i for i in ids if self.db.entity(i)["type"] == m["type"]]
                res.entity_of[key] = (same_type or ids)[0]
                st["exact"] += 1
            else:
                cands = [(i, s) for i, s in self.index.query(
                    "entity", entity_text(m["name"], m["type"], []), self.top_k)
                    if s >= self.min_sim and i not in (self.user_id, self.assistant_id)]
                if not cands:
                    eid = self._new_entity(m["name"], m["type"], m["role"])
                    res.entity_of[key] = eid
                    name_map[key] = [eid]
                    st["new_direct"] += 1
                else:
                    pending.append((key, m, [self._entity_card(i) for i, _ in cands]))

        # thuộc tính
        prop_pending: list[tuple[str, list[str]]] = []
        for ev in events:
            for f in ev.facts:
                p = f.property
                if p in res.property_of:
                    continue
                if self.db.property_by_name(p) is not None:
                    res.property_of[p] = p
                    st["prop_reused"] += 1
                    continue
                hits = self.index.query("property", property_text(p), 3)
                names = [(self.db.conn.execute("SELECT name FROM properties WHERE property_id=?",
                                               (i,)).fetchone()["name"], s) for i, s in hits]
                if names and names[0][1] >= self.prop_auto:
                    res.property_of[p] = names[0][0]
                    st["prop_merged"] += 1
                elif names and names[0][1] >= self.prop_cand:
                    prop_pending.append((p, [n for n, s in names if s >= self.prop_cand]))
                    res.property_of[p] = p                    # mặc định: tạo mới
                else:
                    res.property_of[p] = p
                    st["prop_new"] += 1

        if pending or prop_pending:
            self._ask_llm(res, pending, prop_pending, name_map)
        return res

    def _ask_llm(self, res: Resolution, pending, prop_pending, name_map) -> None:
        st = res.stats
        st["llm_asked"] += len(pending)
        st["llm_calls"] += 1
        mentions_json = [{"mention": m["name"], "type": m["type"], "context": m["ctx"],
                          "candidates": cards} for _, m, cards in pending]
        props_json = [{"proposed": p, "candidates": c} for p, c in prop_pending]
        try:
            out = self.llm.complete_json(PROMPT.format(
                mentions=dumps(mentions_json, indent=1) if mentions_json else "(none)",
                properties=dumps(props_json, indent=1) if props_json else "(none)"),
                role="resolve")
        except LLMFatalError:
            raise
        except LLMError:
            out = {}
            st["llm_failed"] += 1
        decisions = {normalize_name(d.get("mention", "")): d
                     for d in (out.get("entities") or []) if isinstance(d, dict)}
        for key, m, cards in pending:
            d = decisions.get(key, {})
            res.decisions.append({"mention": m["name"], **{k: d.get(k) for k in (
                "decision", "id", "normalized_name", "confidence", "reason")}})
            valid_ids = {c["id"] for c in cards}
            dec = d.get("decision")
            if dec == "choose_existing" and d.get("id") in valid_ids:
                res.entity_of[key] = d["id"]
                self._alias(d["id"], m["name"])
                st["llm_existing"] += 1
            elif dec == "none":
                res.entity_of[key] = None
                st["llm_none"] += 1
            else:
                name = d.get("normalized_name") if isinstance(d.get("normalized_name"), str) \
                    and d.get("normalized_name").strip() else m["name"]
                nkey = normalize_name(name)
                if nkey in name_map:                     # LLM chuẩn hóa ra tên đã có
                    eid = name_map[nkey][0]
                    self._alias(eid, m["name"])
                else:
                    aliases = [a for a in (d.get("aliases") or []) if isinstance(a, str)]
                    if normalize_name(m["name"]) != nkey:
                        aliases.append(m["name"])
                    eid = self._new_entity(name.strip(), d.get("type") or m["type"], m["role"],
                                           aliases)
                    name_map[nkey] = [eid]
                res.entity_of[key] = eid
                st["llm_new"] += 1
        uses = {d.get("proposed"): d.get("use") for d in (out.get("properties") or [])
                if isinstance(d, dict)}
        for p, cands in prop_pending:
            u = uses.get(p)
            if isinstance(u, str) and u in cands:
                res.property_of[p] = u
                st["prop_llm"] += 1
            else:
                st["prop_new"] += 1
