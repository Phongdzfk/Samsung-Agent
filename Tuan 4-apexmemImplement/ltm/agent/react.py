"""Agent ReAct (APEX-MEM §4): suy nghĩ → chọn công cụ → đọc kết quả → lặp, tối đa max_steps.

Hai giao thức:
  - "tools": function calling chuẩn OpenAI (mặc định);
  - "json":  ReAct dạng văn bản, mỗi lượt mô hình trả một JSON {thought, action, args|answer}.
    Dùng khi provider không chuyển tiếp tool calling ổn định.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from ..adapters.llm import BaseLLM, LLMError, LLMFatalError
from ..util import Timer, extract_json, truncate, weekday_of
from .tools import TOOL_SPECS, ToolContext, openai_tools, run_tool

QA_SYSTEM = """You are the memory module of a personal assistant. You answer the user's question
using ONLY the long-term memory built from your past conversations with this user, accessed
through tools.

Current date (the date of the question): {qdate} ({weekday}).
{anchors}
How to work:
1. Plan, then call tools. Start broad (search / entity_lookup), then verify precisely (graph_sql).
2. Memory is append-only and time-stamped. For "current/now/latest" questions use the value with
   the most recent effective time; for "before/first/previously" use history. Compute durations and
   orderings from the dates, relative to the current date above.
3. For counting/aggregation across conversations, enumerate every matching item, de-duplicate,
   then count. Check raw turns when facts look incomplete.
4. Questions about what the assistant said/recommended earlier: search the assistant turns.
5. For preference/recommendation questions, ground the answer in the user's stored preferences.
6. If after searching the information was never mentioned, say you don't know / it was not
   mentioned. Do not guess.
7. Relative time in the question ("two months ago", "last week", "in March"): convert it to a date
   with the reference dates above, then look for events/turns within about +/- 2 weeks of that date
   (graph_sql on events.anchor_datetime or turns.session_date). Pick the item closest to that
   date, NOT simply the most recent one.
8. Who said it matters. Facts with subject "User" and user turns are what the user told you. Facts
   with subject "Assistant" and assistant turns are your own earlier suggestions, estimates or
   general information. If the question asks about the user's own situation (e.g. "how much will I
   save", "what did I pay", "how long did I wait") and the needed value appears only in an
   assistant estimate or nowhere, answer that the information is not enough / was not mentioned.
   Exception: questions that explicitly ask what you (the assistant) said, recommended or listed.
9. Yes/no questions: start with "Yes" or "No", and make it consistent with the evidence you cite.
10. Final answer: short and direct, include the key value (number, name, date). No tool calls in it."""

JSON_PROTOCOL = """

You can call these tools:
{tools}

Reply with EXACTLY one JSON object per message, either
{{"thought": "...", "action": "<tool name>", "args": {{...}}}}
or, when done,
{{"thought": "...", "action": "answer", "answer": "<final answer>"}}
After each tool call you will receive "Observation: ...". """

FORCE_ANSWER = ("You have used the maximum number of tool calls. Give your best final answer now, "
                "based only on what you found. If nothing relevant was found, say you don't know.")


class _Default(dict):
    """format_map giữ nguyên {khóa} lạ → template cũ (chat) không có {anchors} vẫn dùng được."""

    def __missing__(self, key):
        return "{" + key + "}"


def _shift_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 - months, 12)
    y, m = d.year + y, m + 1
    last = [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31,
            30, 31, 30, 31][m - 1]
    return date(y, m, min(d.day, last))


def date_anchors(qdate: str | None) -> str:
    """Python tính sẵn các mốc thời gian tương đối — việc cần chính xác không giao cho LLM nhẩm."""
    if not qdate:
        return ""
    d = datetime.fromisoformat(qdate[:19]).date()
    items = [("yesterday", d - timedelta(days=1)), ("1 week ago", d - timedelta(weeks=1)),
             ("2 weeks ago", d - timedelta(weeks=2)), ("3 weeks ago", d - timedelta(weeks=3)),
             ("1 month ago", _shift_months(d, 1)), ("2 months ago", _shift_months(d, 2)),
             ("3 months ago", _shift_months(d, 3)), ("6 months ago", _shift_months(d, 6)),
             ("1 year ago", _shift_months(d, 12))]
    return "Reference dates: " + "; ".join(f"{k} = {v.isoformat()}" for k, v in items) + ".\n"


@dataclass
class AgentResult:
    answer: str
    steps: list[dict] = field(default_factory=list)
    n_llm_calls: int = 0
    forced: bool = False
    error: str | None = None
    seen_sessions: list[str] = field(default_factory=list)
    sql_errors: int = 0
    ms: float = 0.0


class ReActAgent:
    def __init__(self, llm: BaseLLM, tools: list[str], max_steps: int = 20,
                 protocol: str = "tools", system_template: str = QA_SYSTEM, role: str = "agent"):
        bad = [t for t in tools if t not in TOOL_SPECS]
        if bad:
            raise ValueError(f"công cụ không tồn tại: {bad}")
        self.llm, self.tools, self.max_steps = llm, tools, max_steps
        self.protocol, self.system_template, self.role = protocol, system_template, role

    def system_prompt(self, qdate: str | None) -> str:
        qd = qdate or "unknown"
        fields = {"qdate": qd[:16].replace("T", " "), "weekday": weekday_of(qdate) if qdate else "",
                  "anchors": date_anchors(qdate)}
        s = self.system_template.format_map(_Default(fields))
        if self.protocol == "json":
            specs = "\n".join(f"- {n}({', '.join(TOOL_SPECS[n]['parameters']['properties'])}): "
                              f"{TOOL_SPECS[n]['description']}" for n in self.tools)
            s += JSON_PROTOCOL.format(tools=specs)
        return s

    def run(self, question: str, ctx: ToolContext, history: list[dict] | None = None,
            salt: str = "") -> AgentResult:
        t = Timer()
        with t:
            if self.protocol == "json":
                res = self._run_json(question, ctx, history, salt)
            else:
                res = self._run_tools(question, ctx, history, salt)
        res.ms = t.ms
        res.seen_sessions = sorted(ctx.seen_sessions)
        res.sql_errors = ctx.sql_errors
        return res

    # ---- function calling
    def _run_tools(self, question, ctx, history, salt) -> AgentResult:
        msgs = [{"role": "system", "content": self.system_prompt(ctx.question_date)},
                *(history or []), {"role": "user", "content": question}]
        schemas = openai_tools(self.tools)
        res = AgentResult(answer="")
        try:
            for step in range(self.max_steps + 1):
                last = step == self.max_steps
                if last:
                    msgs.append({"role": "user", "content": FORCE_ANSWER})
                    res.forced = True
                resp = self.llm.chat(msgs, tools=schemas, role=self.role, salt=salt,
                                     tool_choice="none" if last else None)
                res.n_llm_calls += 1
                if not resp.tool_calls or last:
                    res.answer = (resp.content or "").strip()
                    break
                msgs.append({"role": "assistant", "content": resp.content,
                             "tool_calls": [{"id": c["id"], "type": "function",
                                             "function": {"name": c["name"],
                                                          "arguments": c["arguments"]}}
                                            for c in resp.tool_calls]})
                for c in resp.tool_calls:
                    try:
                        args = json.loads(c["arguments"] or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    out, ms = self._exec(ctx, c["name"], args)
                    res.steps.append({"thought": resp.content, "tool": c["name"], "args": args,
                                      "output": truncate(out, 3000), "ms": round(ms)})
                    msgs.append({"role": "tool", "tool_call_id": c["id"], "content": out})
        except LLMFatalError:
            raise
        except LLMError as e:
            res.error = str(e)[:300]
        return res

    # ---- ReAct dạng JSON
    def _run_json(self, question, ctx, history, salt) -> AgentResult:
        msgs = [{"role": "system", "content": self.system_prompt(ctx.question_date)},
                *(history or []), {"role": "user", "content": f"Question: {question}"}]
        res = AgentResult(answer="")
        try:
            for step in range(self.max_steps + 1):
                if step == self.max_steps:
                    msgs.append({"role": "user", "content": FORCE_ANSWER +
                                 ' Reply {"action":"answer","answer":"..."}.'})
                    res.forced = True
                resp = self.llm.chat(msgs, role=self.role, salt=salt)
                res.n_llm_calls += 1
                msgs.append({"role": "assistant", "content": resp.content or ""})
                try:
                    obj = extract_json(resp.content)
                except ValueError:
                    if step == self.max_steps:
                        res.answer = (resp.content or "").strip()
                        break
                    msgs.append({"role": "user", "content": "Reply with ONE valid JSON object."})
                    continue
                action = obj.get("action") if isinstance(obj, dict) else None
                if action == "answer" or step == self.max_steps:
                    res.answer = str(obj.get("answer") or obj.get("thought") or "").strip()
                    break
                args = obj.get("args") if isinstance(obj.get("args"), dict) else {}
                out, ms = self._exec(ctx, str(action), args)
                res.steps.append({"thought": obj.get("thought"), "tool": action, "args": args,
                                  "output": truncate(out, 3000), "ms": round(ms)})
                msgs.append({"role": "user", "content": f"Observation:\n{out}"})
        except LLMFatalError:
            raise
        except LLMError as e:
            res.error = str(e)[:300]
        return res

    def _exec(self, ctx, name, args) -> tuple[str, float]:
        t = Timer()
        with t:
            out = run_tool(ctx, name, args, self.tools)
        return out, t.ms
