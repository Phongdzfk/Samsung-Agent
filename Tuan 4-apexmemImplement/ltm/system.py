"""Lắp ráp toàn hệ từ config: đồ thị SQLite + chỉ mục + luồng ghi + agent đọc."""
from __future__ import annotations

from pathlib import Path

from .adapters.embed import Embedder
from .adapters.llm import BaseLLM
from .agent.react import QA_SYSTEM, AgentResult, ReActAgent
from .agent.tools import ToolContext
from .config import Cfg
from .memory.builder import GraphBuilder
from .memory.extractor import FactExtractor
from .memory.resolver import Resolver
from .store.graphdb import GraphDB
from .store.vector import VectorIndex


class MemorySystem:
    def __init__(self, cfg: Cfg, db_path: str | Path, llm: BaseLLM, embedder: Embedder):
        self.cfg, self.llm, self.embedder = cfg, llm, embedder
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self.db = GraphDB(db_path)
        self.index = VectorIndex(self.db, embedder)
        x, r = cfg.extract, cfg.resolve
        self.extractor = FactExtractor(llm, self.db.ontology, x.turns_per_call, x.max_turn_chars,
                                       x.include_assistant)
        self.resolver = Resolver(self.db, self.index, llm, r.top_k, r.min_candidate_sim,
                                 r.prop_auto_merge_sim, r.prop_candidate_sim)
        self.builder = GraphBuilder(self.db, self.index, self.extractor, self.resolver)

    def tool_context(self, question_date: str | None) -> ToolContext:
        a = self.cfg.agent
        return ToolContext(self.db, self.index, question_date, a.search_k, a.max_tool_chars)

    def agent(self, tools: list[str] | None = None, max_steps: int | None = None,
              protocol: str | None = None, system_template: str = QA_SYSTEM,
              llm: BaseLLM | None = None) -> ReActAgent:
        a = self.cfg.agent
        return ReActAgent(llm or self.llm, list(tools or a.tools), max_steps or a.max_steps,
                          protocol or a.protocol, system_template)

    def answer(self, question: str, question_date: str | None, *, tools: list[str] | None = None,
               max_steps: int | None = None, salt: str = "",
               llm: BaseLLM | None = None) -> AgentResult:
        ctx = self.tool_context(question_date)
        return self.agent(tools, max_steps, llm=llm).run(question, ctx, salt=salt)

    def close(self) -> None:
        self.db.close()
