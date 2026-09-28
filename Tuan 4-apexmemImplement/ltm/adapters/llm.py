"""Adapter LLM duy nhất của hệ: mọi lời gọi mô hình đi qua đây.

- Gọi endpoint OpenAI-compatible (9router: http://localhost:20128/v1).
- Cache theo sha1(model + messages + tools + tham số + salt): chạy lại eval KHÔNG tốn hạn mức.
- 429 / 5xx / mất kết nối: chờ lũy thừa rồi thử lại (khi mọi tài khoản 9router đều hết hạn mức,
  9router trả lỗi → ở đây chờ tới khi có tài khoản hồi lại).
- Ghi lại MODEL THỰC SỰ PHỤC VỤ (response.model) cho từng lời gọi → phát hiện router lén đổi mô hình.
"""
from __future__ import annotations

import os
import random
import sqlite3
import threading
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from ..util import dumps, extract_json, sha1


class LLMError(RuntimeError):
    pass


class LLMJSONError(LLMError):
    pass


class LLMFatalError(LLMError):
    """Lỗi cấu hình (sai key, sai tên model, tài khoản không có quyền dùng model).

    KHÔNG được nuốt ở tầng trích xuất/giải quyết: nếu nuốt, đồ thị được dựng rỗng rồi bị đánh dấu
    "đã xong" → số liệu hỏng âm thầm. Lỗi này làm dừng câu hỏi hiện tại (không ghi kết quả).
    """


class ModelMismatchError(LLMError):
    pass


@dataclass
class LLMResponse:
    content: str | None
    tool_calls: list[dict] = field(default_factory=list)   # [{"id","name","arguments"(str)}]
    model: str = ""
    usage: dict = field(default_factory=dict)
    latency_ms: float = 0.0
    cached: bool = False

    def to_json(self) -> dict:
        return {"content": self.content, "tool_calls": self.tool_calls, "model": self.model,
                "usage": self.usage}


# ---------------------------------------------------------------- đồng hồ đo sử dụng

class UsageMeter:
    """Đếm lời gọi / token / độ trễ theo vai trò (extract, resolve, agent, judge...)."""

    def __init__(self):
        self._lock = threading.Lock()
        self.calls: Counter = Counter()
        self.cached: Counter = Counter()
        self.prompt_tokens: Counter = Counter()
        self.completion_tokens: Counter = Counter()
        self.latency: dict[str, list[float]] = defaultdict(list)
        self.served: Counter = Counter()
        self.mismatch: Counter = Counter()

    def record(self, role: str, resp: LLMResponse, mismatch: bool = False) -> None:
        with self._lock:
            self.calls[role] += 1
            if resp.cached:
                self.cached[role] += 1
            self.prompt_tokens[role] += int(resp.usage.get("prompt_tokens") or 0)
            self.completion_tokens[role] += int(resp.usage.get("completion_tokens") or 0)
            if not resp.cached:
                self.latency[role].append(resp.latency_ms)
            self.served[resp.model or "unknown"] += 1
            if mismatch:
                self.mismatch[role] += 1

    def snapshot(self) -> dict:
        with self._lock:
            roles = set(self.calls) | set(self.latency)
            return {
                r: {"calls": self.calls[r], "cached": self.cached[r],
                    "prompt_tokens": self.prompt_tokens[r],
                    "completion_tokens": self.completion_tokens[r],
                    "latency_ms": round(sum(self.latency[r]), 1),
                    "mismatch": self.mismatch[r]}
                for r in roles
            } | {"_served_models": dict(self.served)}

    @staticmethod
    def diff(after: dict, before: dict) -> dict:
        out = {}
        for r, v in after.items():
            if r == "_served_models":
                b = before.get(r, {})
                d = {m: c - b.get(m, 0) for m, c in v.items() if c - b.get(m, 0)}
                out[r] = d
                continue
            b = before.get(r, {})
            d = {k: round(v[k] - b.get(k, 0), 1) for k in v}
            if any(d.values()):
                out[r] = d
        return out


# ---------------------------------------------------------------- cache

class LLMCache:
    def __init__(self, path: str | Path):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("CREATE TABLE IF NOT EXISTS llm_cache (key TEXT PRIMARY KEY, "
                          "model TEXT, response TEXT, created TEXT DEFAULT CURRENT_TIMESTAMP)")
        self._lock = threading.Lock()

    def get(self, key: str) -> dict | None:
        with self._lock:
            row = self.conn.execute("SELECT response FROM llm_cache WHERE key=?", (key,)).fetchone()
        import json
        return json.loads(row[0]) if row else None

    def put(self, key: str, model: str, resp: dict) -> None:
        with self._lock, self.conn:
            self.conn.execute("INSERT OR REPLACE INTO llm_cache(key, model, response) VALUES (?,?,?)",
                              (key, model, dumps(resp)))


# ---------------------------------------------------------------- lớp cơ sở

class BaseLLM:
    meter: UsageMeter

    def model_for(self, role: str) -> str:
        return "base"

    def chat(self, messages: list[dict], *, tools: list[dict] | None = None,
             role: str = "default", salt: str = "", tool_choice: str | None = None) -> LLMResponse:
        raise NotImplementedError

    def complete_text(self, prompt: str, *, role: str = "default", system: str | None = None,
                      salt: str = "") -> str:
        msgs = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}]
        return self.chat(msgs, role=role, salt=salt).content or ""

    def complete_json(self, prompt: str, *, role: str = "default", system: str | None = None,
                      salt: str = "") -> Any:
        msgs = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": prompt}]
        resp = self.chat(msgs, role=role, salt=salt)
        try:
            return extract_json(resp.content)
        except ValueError:
            msgs = msgs + [{"role": "assistant", "content": resp.content or ""},
                           {"role": "user", "content": "Your reply was not valid JSON. "
                                                       "Return ONLY the JSON object, nothing else."}]
            resp2 = self.chat(msgs, role=role, salt=salt)
            try:
                return extract_json(resp2.content)
            except ValueError as e:
                raise LLMJSONError(str(e)) from None


def same_model(requested: str, served: str) -> bool:
    """'cx/gpt-5.5' khớp 'gpt-5.5', 'gpt-5.5-2026-04-01', 'cx/gpt-5.5'. Chuỗi rỗng = không biết."""
    if not served:
        return True
    a = requested.split("/")[-1].lower()
    b = served.split("/")[-1].lower()
    return a == b or b.startswith(a) or a.startswith(b)


# ---------------------------------------------------------------- client thật

class OpenAICompatLLM(BaseLLM):
    def __init__(self, cfg: dict, meter: UsageMeter | None = None, cache: LLMCache | None = None):
        from openai import OpenAI  # import muộn: test offline không cần gói này

        self.cfg = cfg
        key = os.environ.get(cfg.get("api_key_env") or "", "") or "sk-no-key"
        self.client = OpenAI(api_key=key, base_url=cfg["base_url"],
                             timeout=cfg.get("timeout", 300), max_retries=0)
        self.meter = meter or UsageMeter()
        from ..config import resolve_path
        self.cache = cache if cache is not None else (
            LLMCache(resolve_path(cfg["cache_path"])) if cfg.get("cache_path") else None)
        self._drop_temperature = False

    def model_for(self, role: str) -> str:
        return (self.cfg.get("roles") or {}).get(role) or self.cfg["model"]

    def _params(self, model: str) -> dict:
        p: dict[str, Any] = {"model": model}
        if self.cfg.get("temperature") is not None and not self._drop_temperature:
            p["temperature"] = self.cfg["temperature"]
        if self.cfg.get("reasoning_effort"):
            p["reasoning_effort"] = self.cfg["reasoning_effort"]
        if self.cfg.get("max_tokens"):
            p["max_tokens"] = self.cfg["max_tokens"]
        return p

    def chat(self, messages, *, tools=None, role="default", salt="", tool_choice=None):
        model = self.model_for(role)
        params = self._params(model)
        if tools and tool_choice:
            params["tool_choice"] = tool_choice
        key = sha1(dumps({"p": params, "m": messages, "t": tools, "s": salt}, sort_keys=True))
        if self.cache:
            hit = self.cache.get(key)
            if hit is not None:
                resp = LLMResponse(hit["content"], hit.get("tool_calls") or [], hit.get("model", ""),
                                   hit.get("usage") or {}, 0.0, cached=True)
                self.meter.record(role, resp)
                return resp

        resp = self._call_with_retry(messages, tools, params)
        mismatch = not same_model(model, resp.model)
        self.meter.record(role, resp, mismatch)
        if mismatch and self.cfg.get("strict_model"):
            raise ModelMismatchError(f"yêu cầu {model} nhưng được phục vụ bởi {resp.model}")
        if self.cache and not mismatch:
            self.cache.put(key, resp.model, resp.to_json())
        return resp

    def _call_with_retry(self, messages, tools, params) -> LLMResponse:
        import openai

        max_retries = int(self.cfg.get("max_retries", 8))
        max_wait = float(self.cfg.get("max_wait", 600))
        last: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                return self._call(messages, tools, params)
            except openai.BadRequestError as e:
                msg = str(e).lower()
                if "temperature" in params and "temperature" in msg and not self._drop_temperature:
                    self._drop_temperature = True          # model lý luận không nhận temperature
                    params = {k: v for k, v in params.items() if k != "temperature"}
                    continue
                raise LLMError(f"bad_request: {e}") from None
            except openai.AuthenticationError as e:
                raise LLMFatalError(f"auth: kiểm tra API key 9router ({e})") from None
            except openai.NotFoundError as e:
                raise LLMFatalError(
                    f"model '{params.get('model')}' không dùng được ({e}). Tài khoản trong 9router "
                    "không có quyền dùng model này, hoặc sai tên model — chạy python -m ltm.check"
                ) from None
            except (openai.RateLimitError, openai.APIConnectionError, openai.APITimeoutError,
                    openai.InternalServerError) as e:
                last = e
            except openai.APIStatusError as e:
                if e.status_code in (408, 409, 425, 429) or e.status_code >= 500:
                    last = e
                elif e.status_code in (401, 403, 404):
                    raise LLMFatalError(f"http_{e.status_code}: {e}") from None
                else:
                    raise LLMError(f"http_{e.status_code}: {e}") from None
            wait = min(max_wait, 5 * 2 ** attempt) * (0.8 + 0.4 * random.random())
            print(f"[llm] {type(last).__name__}: chờ {wait:.0f}s rồi thử lại "
                  f"({attempt + 1}/{max_retries})", flush=True)
            time.sleep(wait)
        raise LLMError(f"hết lượt thử lại: {last}")

    def _call(self, messages, tools, params) -> LLMResponse:
        kw = dict(params, messages=messages)
        if tools:
            kw["tools"] = tools
        t0 = time.perf_counter()
        if not self.cfg.get("stream"):
            r = self.client.chat.completions.create(**kw)
            msg = r.choices[0].message
            calls = [{"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments or "{}"}
                     for tc in (msg.tool_calls or [])]
            usage = {"prompt_tokens": getattr(r.usage, "prompt_tokens", 0) if r.usage else 0,
                     "completion_tokens": getattr(r.usage, "completion_tokens", 0) if r.usage else 0}
            return LLMResponse(msg.content, calls, r.model or "", usage,
                               (time.perf_counter() - t0) * 1000)
        # stream: ghép các mảnh nội dung và tool_call
        kw["stream"] = True
        kw["stream_options"] = {"include_usage": True}
        content, model, usage = [], "", {}
        calls: dict[int, dict] = {}
        for chunk in self.client.chat.completions.create(**kw):
            model = chunk.model or model
            if getattr(chunk, "usage", None):
                usage = {"prompt_tokens": chunk.usage.prompt_tokens,
                         "completion_tokens": chunk.usage.completion_tokens}
            if not chunk.choices:
                continue
            d = chunk.choices[0].delta
            if d.content:
                content.append(d.content)
            for tc in d.tool_calls or []:
                c = calls.setdefault(tc.index, {"id": "", "name": "", "arguments": ""})
                c["id"] = tc.id or c["id"]
                if tc.function:
                    c["name"] += tc.function.name or ""
                    c["arguments"] += tc.function.arguments or ""
        return LLMResponse("".join(content) or None, [calls[i] for i in sorted(calls)], model, usage,
                           (time.perf_counter() - t0) * 1000)


# ---------------------------------------------------------------- giả lập (test offline)

Handler = Callable[[list[dict], list[dict] | None], Any]


class FakeLLM(BaseLLM):
    """LLM giả: mỗi vai trò có một hàm hoặc một hàng đợi câu trả lời.

    Câu trả lời là str (nội dung) hoặc dict {"content":..., "tool_calls":[{"name","arguments"}]}.
    """

    def __init__(self, handlers: dict[str, Handler | list] | None = None, default: Any = "{}"):
        self.handlers = handlers or {}
        self.default = default
        self.meter = UsageMeter()
        self.log: list[tuple[str, list[dict]]] = []

    def model_for(self, role):
        return "fake"

    def chat(self, messages, *, tools=None, role="default", salt="", tool_choice=None):
        self.log.append((role, messages))
        if tools and tool_choice == "none":
            tools = None
        h = self.handlers.get(role, self.default)
        if isinstance(h, list):
            out = h.pop(0) if h else "{}"
        elif callable(h):
            out = h(messages, tools)
        else:
            out = h
        if isinstance(out, dict) and ("content" in out or "tool_calls" in out):
            calls = []
            for i, c in enumerate(out.get("tool_calls") or []):
                args = c.get("arguments", {})
                calls.append({"id": c.get("id", f"call_{len(self.log)}_{i}"), "name": c["name"],
                              "arguments": args if isinstance(args, str) else dumps(args)})
            resp = LLMResponse(out.get("content"), calls, "fake", {"prompt_tokens": 1})
        else:
            resp = LLMResponse(out if isinstance(out, str) else dumps(out), [], "fake",
                               {"prompt_tokens": 1})
        self.meter.record(role, resp)
        return resp


def build_llm(cfg_llm: dict, meter: UsageMeter | None = None) -> BaseLLM:
    return OpenAICompatLLM(cfg_llm, meter=meter)


class ScopedLLM(BaseLLM):
    """Bọc một LLM dùng chung, đếm riêng cho một phạm vi (một câu hỏi, một pha).

    Chạy song song nhiều câu hỏi vẫn tách được chi phí từng câu, từng pha dựng/trả lời/chấm.
    """

    def __init__(self, inner: BaseLLM):
        self.inner = inner
        self.meter = UsageMeter()

    def model_for(self, role):
        return self.inner.model_for(role)

    def chat(self, messages, *, tools=None, role="default", salt="", tool_choice=None):
        r = self.inner.chat(messages, tools=tools, role=role, salt=salt, tool_choice=tool_choice)
        self.meter.record(role, r, mismatch=not same_model(self.inner.model_for(role), r.model)
                          if r.model != "fake" else False)
        return r
