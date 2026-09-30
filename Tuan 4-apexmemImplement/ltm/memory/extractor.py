"""Bước 2 luồng ghi — trích xuất sự kiện + fact có mốc thời gian (gọi LLM).

Theo APEX-MEM §3.2: mỗi đoạn hội thoại → các sự kiện theo ontology; mỗi sự kiện có loại, thời
điểm, địa điểm, người tham gia, danh sách fact và bằng chứng. Thời gian quy về ISO 8601 theo
ngày của phiên.

Khác bài báo (vì chi phí): gom `turns_per_call` lượt vào một lời gọi thay vì một lượt/lời gọi.
Mọi kiểm tra kiểu dữ liệu làm bằng Python; fact hỏng bị loại kèm mã lý do để thống kê.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from ..adapters.llm import BaseLLM, LLMError, LLMFatalError
from ..store.graphdb import DTYPES, ROLES
from ..util import coerce_iso, truncate, weekday_of

PROPERTY_RE = re.compile(r"^[a-z][a-z0-9_]*$")


@dataclass
class XFact:
    subject: str
    subject_type: str
    property: str
    dtype: str
    value: Any
    t_from: str | None
    t_to: str | None
    confidence: float
    evidence_turn: int
    span: str | None = None


@dataclass
class XEvent:
    type: str
    anchor_datetime: str
    location: str | None
    participants: list[tuple[str, str, str]]          # (name, type, role)
    facts: list[XFact] = field(default_factory=list)


SYSTEM = ("You are an information-extraction engine that turns conversations into a temporal "
          "knowledge graph for a personal assistant's long-term memory. Output JSON only.")

PROMPT = """Extract structured memory from the conversation excerpt below.

SESSION_DATE: {date} ({weekday})
{context}TURNS (index. SPEAKER: text):
{turns}

Represent what is said as EVENTS. An event is something that happened, was stated, decided,
planned, bought, learned, recommended or computed. Each event:
- "type": short snake_case label (purchase, trip, exam_result, recommendation, preference_statement,
  plan, life_event, health_update, work_update, hobby_activity, conversation_topic, ...)
- "anchor_datetime": when it happened, ISO 8601 (YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS). Resolve relative
  expressions ("yesterday", "last month", "two weeks ago", "next Friday") against SESSION_DATE.
  If unknown, use SESSION_DATE.
- "location": place or null
- "participants": [{{"name","type","role"}}] with role in Speaker|Listener|Agent|Mentioned
- "facts": subject-property-value facts supported by the event.

Each fact:
- "subject": entity name. Use exactly "User" for the user and "Assistant" for the assistant.
- "subject_type": one class from ONTOLOGY
- "property": English snake_case ASCII, specific and reusable (japanese_level, home_city,
  favorite_cuisine, pet_name, job_title, purchase_price, number_of_children). Never put the value
  inside the property name.
- "dtype": one of str,int,float,bool,date,datetime,enum,url,list
- "value": matches dtype (numbers as numbers, dates ISO, list as JSON array)
- "t_from": when the fact became true (default anchor_datetime); "t_to": only if the text says it ended
- "confidence": 0..1
- "evidence_turn": index of the supporting turn
- "span": short verbatim quote from that turn

Rules:
- Capture the user's life: preferences, possessions, people, pets, jobs, places, plans, habits,
  purchases, numbers, dates, durations, counts, and changes over time.
- Every activity the user mentions (visit, trip, class, purchase, event attended, lecture,
  appointment...) is its OWN event, even when mentioned only in passing ("by the way, I just...",
  "I went to ... last week"). Do not merge different activities into one event.
- For each such event always record WHERE ("location" + the place as a participant) and WITH WHOM:
  add every companion as a participant (people named only by relation get a descriptive name,
  e.g. "User's father", "User's friend (chemistry professor)") and a fact
  {{"subject":"User","property":"companion", "value":"<who>"}} tied to that event. If the text says
  the user went alone, record companion = "alone".
- Numbers with units or currencies: if the property name contains a unit (price_usd, duration_min)
  the value MUST be in exactly that unit. Otherwise keep the unit in the value as a string
  ("¥3,200", "45 minutes") or add a separate fact <property>_currency / <property>_unit.
  Never guess a unit or currency that the text does not state.
- Also capture what the ASSISTANT recommended, listed, calculated or promised (subject "Assistant",
  e.g. recommended_restaurants as a list in the given order).
- Keep exact details: names, titles, brands, amounts, prices, times, ordering.
- Skip greetings, chit-chat and generic world knowledge.
- Nothing worth remembering -> {{"events": []}}

ONTOLOGY: {ontology}

Example output:
{{"events":[{{"type":"exam_result","anchor_datetime":"2024-01-20","location":null,
 "participants":[{{"name":"User","type":"Person","role":"Speaker"}},
                 {{"name":"JLPT","type":"Contract","role":"Mentioned"}}],
 "facts":[{{"subject":"User","subject_type":"Person","property":"japanese_level","dtype":"enum",
   "value":"N4","t_from":"2024-01-20","t_to":null,"confidence":0.95,"evidence_turn":3,
   "span":"I passed the N4 last Saturday"}}]}}]}}

Return ONLY the JSON object."""


class Rejected(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(reason)
        self.reason, self.detail = reason, detail


def normalize_property(name: Any) -> tuple[str, bool]:
    """Sửa những lỗi hình thức vô hại (hoa, cách, gạch ngang). Trả (tên, đã_sửa)."""
    if not isinstance(name, str) or not name.strip():
        raise Rejected("property_empty")
    if not name.isascii():
        raise Rejected("property_not_ascii", name)
    fixed = re.sub(r"[\s\-./]+", "_", name.strip().lower())
    fixed = re.sub(r"_+", "_", fixed).strip("_")
    if not PROPERTY_RE.match(fixed):
        raise Rejected("property_bad_format", name)
    return fixed, fixed != name


def coerce_value(value: Any, dtype: str) -> tuple[Any, str]:
    """Ép giá trị về dtype; không ép được thì hạ về 'str' (giữ thông tin, không vứt fact)."""
    if value is None or (isinstance(value, str) and not value.strip()) or value == []:
        raise Rejected("value_empty")
    if dtype not in DTYPES:
        dtype = "list" if isinstance(value, list) else "str"
    try:
        if dtype in ("str", "enum"):
            if isinstance(value, (dict, list)):
                return (", ".join(map(str, value)) if isinstance(value, list) else str(value)), "str"
            return str(value), dtype
        if dtype == "int":
            if isinstance(value, bool):
                raise ValueError
            f = float(str(value).replace(",", ""))
            if f.is_integer():
                return int(f), "int"
            return f, "float"
        if dtype == "float":
            if isinstance(value, bool):
                raise ValueError
            return float(str(value).replace(",", "")), "float"
        if dtype == "bool":
            if isinstance(value, bool):
                return value, "bool"
            s = str(value).strip().lower()
            if s in ("true", "yes", "1"):
                return True, "bool"
            if s in ("false", "no", "0"):
                return False, "bool"
            raise ValueError
        if dtype == "date":
            iso = coerce_iso(str(value))
            if not iso:
                raise ValueError
            return iso[:10], "date"
        if dtype == "datetime":
            iso = coerce_iso(str(value))
            if not iso:
                raise ValueError
            return (iso if len(iso) > 10 else iso + "T00:00:00"), "datetime"
        if dtype == "list":
            return (value if isinstance(value, list) else [value]), "list"
        if dtype == "url":
            s = str(value)
            if s.startswith(("http://", "https://")):
                return s, "url"
            raise ValueError
    except (ValueError, TypeError):
        pass
    return (", ".join(map(str, value)) if isinstance(value, list) else str(value)), "str"


class FactExtractor:
    def __init__(self, llm: BaseLLM, ontology: frozenset[str], turns_per_call: int = 12,
                 max_turn_chars: int = 3000, include_assistant: bool = True):
        self.llm, self.ontology = llm, ontology
        self.turns_per_call, self.max_turn_chars = turns_per_call, max_turn_chars
        self.include_assistant = include_assistant

    # ---- một phiên → nhiều đoạn → nhiều sự kiện
    def extract_session(self, session_date: str, turns: list[tuple[int, str, str]]
                        ) -> tuple[list[XEvent], list[dict], dict]:
        """turns: [(turn_index, speaker, text)]. Trả (events, rejected, stats)."""
        events: list[XEvent] = []
        rejected: list[dict] = []
        stats = {"chunks": 0, "llm_failed": 0, "facts": 0, "normalized_property": 0,
                 "dtype_fallback": 0}
        n = self.turns_per_call
        for start in range(0, len(turns), n):
            chunk = turns[start:start + n]
            context = turns[max(0, start - 2):start]
            stats["chunks"] += 1
            try:
                raw = self.llm.complete_json(self._prompt(session_date, chunk, context),
                                             role="extract", system=SYSTEM)
            except LLMFatalError:
                raise
            except LLMError as e:
                stats["llm_failed"] += 1
                rejected.append({"reason": "llm_failed", "detail": str(e)[:200]})
                continue
            evs, rej = self.parse(raw, session_date, {i for i, _, _ in chunk}, stats)
            events += evs
            rejected += rej
        stats["facts"] = sum(len(e.facts) for e in events)
        return events, rejected, stats

    def _prompt(self, session_date, chunk, context) -> str:
        def fmt(rows):
            return "\n".join(f"{i}. {'USER' if sp == 'user' else 'ASSISTANT'}: "
                             f"{truncate(tx, self.max_turn_chars)}" for i, sp, tx in rows)
        ctx = (f"CONTEXT (earlier turns, do NOT extract from these):\n{fmt(context)}\n\n"
               if context else "")
        return PROMPT.format(date=session_date[:10], weekday=weekday_of(session_date),
                             context=ctx, turns=fmt(chunk),
                             ontology=", ".join(sorted(self.ontology)))

    # ---- JSON thô → XEvent đã kiểm tra
    def parse(self, raw: Any, session_date: str, valid_turns: set[int],
              stats: dict | None = None) -> tuple[list[XEvent], list[dict]]:
        stats = stats if stats is not None else {}
        rejected: list[dict] = []
        if isinstance(raw, list):
            raw = {"events": raw}
        if not isinstance(raw, dict) or not isinstance(raw.get("events"), list):
            return [], [{"reason": "bad_json_shape"}]
        out = []
        for ev in raw["events"]:
            if not isinstance(ev, dict):
                rejected.append({"reason": "bad_event"})
                continue
            anchor = coerce_iso(ev.get("anchor_datetime")) or session_date
            etype = ev.get("type") if isinstance(ev.get("type"), str) and ev.get("type") else "event"
            etype = re.sub(r"[^a-z0-9_]+", "_", etype.lower()).strip("_") or "event"
            parts = []
            for p in ev.get("participants") or []:
                if isinstance(p, dict) and isinstance(p.get("name"), str) and p["name"].strip():
                    parts.append((p["name"].strip(), self._etype(p.get("type"), p["name"]),
                                  p.get("role") if p.get("role") in ROLES else "Mentioned"))
            facts = []
            for f in ev.get("facts") or []:
                try:
                    facts.append(self._fact(f, anchor, valid_turns, stats))
                except Rejected as r:
                    rejected.append({"reason": r.reason, "detail": r.detail,
                                     "property": f.get("property") if isinstance(f, dict) else None})
            if facts or parts:
                out.append(XEvent(etype, anchor, ev.get("location") if isinstance(
                    ev.get("location"), str) else None, parts, facts))
        return out, rejected

    def _etype(self, t: Any, name: str = "") -> str:
        if name.strip().lower() in ("user", "assistant"):
            return "Person" if name.strip().lower() == "user" else "Software"
        return t if isinstance(t, str) and t in self.ontology else "Other"

    def _fact(self, f: Any, anchor: str, valid_turns: set[int], stats: dict) -> XFact:
        if not isinstance(f, dict):
            raise Rejected("bad_fact")
        subj = f.get("subject")
        if not isinstance(subj, str) or not subj.strip():
            raise Rejected("subject_empty")
        prop, fixed = normalize_property(f.get("property"))
        if fixed:
            stats["normalized_property"] = stats.get("normalized_property", 0) + 1
        dtype_in = f.get("dtype") if f.get("dtype") in DTYPES else "str"
        value, dtype = coerce_value(f.get("value"), dtype_in)
        if dtype != dtype_in:
            stats["dtype_fallback"] = stats.get("dtype_fallback", 0) + 1
        try:
            turn = int(f.get("evidence_turn"))
        except (TypeError, ValueError):
            raise Rejected("bad_evidence_turn", str(f.get("evidence_turn"))) from None
        if turn not in valid_turns:
            raise Rejected("bad_evidence_turn", str(turn))
        t_from = coerce_iso(f.get("t_from")) or anchor
        t_to = coerce_iso(f.get("t_to"))
        if t_to and t_to < t_from:
            t_to = None
        try:
            conf = min(1.0, max(0.0, float(f.get("confidence", 0.8))))
        except (TypeError, ValueError):
            conf = 0.8
        span = f.get("span") if isinstance(f.get("span"), str) else None
        return XFact(subj.strip(), self._etype(f.get("subject_type"), subj), prop, dtype, value,
                     t_from, t_to, conf, turn, span)
