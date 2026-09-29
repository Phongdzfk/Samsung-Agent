"""Kiểm tra môi trường trước khi chạy thật:  python -m ltm.check

1. 9router có chạy không, API key đúng không, có những model nào.
2. Mỗi vai trò (extract/resolve/agent/judge) gọi được model của nó không, model THỰC SỰ phục vụ là gì.
3. Function calling có đi qua 9router không (nếu không → đặt agent.protocol: json).
4. Dữ liệu LongMemEval và cache embedding Kaggle đã đặt đúng chỗ chưa.
"""
from __future__ import annotations

import os
import sys

from .adapters.embed import EmbedCache
from .adapters.llm import LLMError, OpenAICompatLLM, same_model
from .agent.tools import openai_tools
from .config import load_config, resolve_path


def main() -> int:
    cfg = load_config()
    ok = True
    print(f"== 9router: {cfg.llm.base_url}")
    key_env = cfg.llm.api_key_env
    if not os.environ.get(key_env):
        print(f"  ⚠ chưa đặt biến môi trường {key_env} (API key trong dashboard 9router)")
    llm = OpenAICompatLLM(cfg.llm, cache=None)
    llm.cache = None
    try:
        models = [m.id for m in llm.client.models.list().data]
        print(f"  ✓ kết nối được · {len(models)} model")
        for want in {llm.model_for(r) for r in ("extract", "resolve", "agent", "reader", "judge")}:
            print(f"    {'✓' if want in models else '?'} {want}"
                  + ("" if want in models else "  (không thấy trong /v1/models — kiểm tra tên)"))
    except Exception as e:
        print(f"  ✗ không kết nối được: {e}\n    → đã chạy `9router` chưa? mở http://localhost:20128")
        return 1

    print("== Gọi thử từng vai trò")
    for role in ("extract", "agent", "judge"):
        try:
            r = llm.chat([{"role": "user", "content": "Reply with the single word: pong"}],
                         role=role, salt=f"check-{os.getpid()}")
            flag = "✓" if same_model(llm.model_for(role), r.model) else "⚠ KHÁC MODEL"
            print(f"  {flag} {role}: yêu cầu {llm.model_for(role)} → phục vụ bởi "
                  f"'{r.model or '?'}' · {r.latency_ms:.0f} ms · trả lời {r.content!r:.40}")
        except LLMError as e:
            ok = False
            print(f"  ✗ {role}: {e}")

    print("== Function calling qua 9router")
    try:
        r = llm.chat([{"role": "user", "content": "Use the search tool to look up 'Tokyo trip'."}],
                     tools=openai_tools(["search"]), role="agent", salt=f"check-tools-{os.getpid()}")
        if r.tool_calls:
            print(f"  ✓ nhận được tool call: {r.tool_calls[0]['name']}({r.tool_calls[0]['arguments']})")
        else:
            print("  ⚠ model không gọi công cụ → đặt agent.protocol: json trong config.yaml")
    except LLMError as e:
        print(f"  ✗ lỗi khi gửi tools: {e}\n    → đặt agent.protocol: json trong config.yaml")

    print("== Dữ liệu")
    ds = resolve_path(cfg.eval.dataset_path)
    print(f"  {'✓' if ds.exists() else '✗'} {ds}"
          + ("" if ds.exists() else "  → python -m ltm.eval.download"))
    ok &= ds.exists()
    cp = resolve_path(cfg.embed.cache_path)
    n = EmbedCache(cp).count(cfg.embed.model) if cp.exists() else 0
    print(f"  {'✓' if n > 100_000 else '⚠'} cache embedding {cp}: {n:,} vector ({cfg.embed.model})"
          + ("" if n > 100_000 else "  → chạy kaggle/embed_longmemeval.py rồi tải file về đây"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
