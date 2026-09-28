"""LLM giả có "hiểu biết" tối thiểu để chạy toàn pipeline offline, không tốn hạn mức."""
from __future__ import annotations

import json
import re

from ltm.adapters.embed import HashEmbedder
from ltm.adapters.llm import FakeLLM
from ltm.config import load_config

TURN_RE = re.compile(r"^(\d+)\. (USER|ASSISTANT): (.*)$", re.M)


def turns_in(prompt: str) -> list[tuple[int, str, str]]:
    body = prompt.split("TURNS (index. SPEAKER: text):", 1)[1].split("Represent what", 1)[0]
    return [(int(i), sp, tx) for i, sp, tx in TURN_RE.findall(body)]


def session_date(prompt: str) -> str:
    return re.search(r"SESSION_DATE: (\S+)", prompt).group(1)


def fake_extract(messages, tools):
    prompt = messages[-1]["content"]
    d = session_date(prompt)
    events = []
    for i, sp, tx in turns_in(prompt):
        m = re.search(r"\b(N[1-5])\b", tx)
        if m and sp == "USER":
            events.append({"type": "exam_result", "anchor_datetime": d, "location": None,
                           "participants": [{"name": "User", "type": "Person", "role": "Speaker"}],
                           "facts": [{"subject": "User", "subject_type": "Person",
                                      "property": "japanese_level", "dtype": "enum",
                                      "value": m.group(1), "t_from": d, "t_to": None,
                                      "confidence": 0.9, "evidence_turn": i, "span": m.group(1)}]})
        m = re.search(r"trip to (\w+)", tx, re.I)
        if m and sp == "USER":
            city = m.group(1)
            events.append({"type": "trip", "anchor_datetime": d, "location": city,
                           "participants": [{"name": "User", "type": "Person", "role": "Speaker"},
                                            {"name": city, "type": "Place", "role": "Mentioned"}],
                           "facts": [{"subject": "User", "subject_type": "Person",
                                      "property": "visited_city", "dtype": "str", "value": city,
                                      "t_from": d, "confidence": 0.8, "evidence_turn": i},
                                     {"subject": city, "subject_type": "Place",
                                      "property": "country", "dtype": "str", "value": "Japan",
                                      "confidence": 0.7, "evidence_turn": i}]})
        m = re.search(r"I recommend (.+?)\.", tx)
        if m and sp == "ASSISTANT":
            events.append({"type": "recommendation", "anchor_datetime": d,
                           "participants": [{"name": "Assistant", "type": "Software",
                                             "role": "Agent"}],
                           "facts": [{"subject": "Assistant", "property": "recommended_items",
                                      "dtype": "list", "value": [x.strip() for x in
                                                                 m.group(1).split(",")],
                                      "evidence_turn": i}]})
    return json.dumps({"events": events})


def fake_resolve(messages, tools):
    # luôn chọn ứng viên đầu tiên nếu có (đủ cho test)
    prompt = messages[-1]["content"]
    ents = []
    block = prompt.split("ENTITY MENTIONS:", 1)[1].split("PROPERTIES:", 1)[0].strip()
    if block != "(none)":
        for m in json.loads(block):
            c = m["candidates"]
            ents.append({"mention": m["mention"], "decision": "choose_existing",
                         "id": c[0]["id"]} if c else {"mention": m["mention"],
                                                      "decision": "propose_new"})
    return json.dumps({"entities": ents, "properties": []})


def fake_judge(messages, tools):
    p = messages[-1]["content"]
    gold = re.search(r"(?:Correct Answer|Explanation|Rubric): (.*)", p).group(1).strip()
    resp = p.split("Model Response:", 1)[1].split("\n\n")[0]
    return "yes" if gold.lower() in resp.lower() or "not mentioned" in resp.lower() else "no"


def agent_script():
    """Agent giả: tra User → trả lời bằng giá trị mới nhất tìm thấy trong kết quả công cụ."""
    def h(messages, tools):
        tool_msgs = [m for m in messages if m["role"] == "tool"]
        if not tool_msgs and tools:
            return {"content": None, "tool_calls": [{"name": "entity_lookup",
                                                     "arguments": {"query": "User"}}]}
        text = tool_msgs[-1]["content"] if tool_msgs else ""
        question = [m for m in messages if m["role"] == "user"][-1]["content"].lower()
        if "level" not in question:
            return {"content": "It was not mentioned."}
        m = re.search(r"\| japanese_level \| (N\d)", text)
        return {"content": m.group(1) if m else "It was not mentioned."}
    return h


def make_llm(**extra):
    handlers = {"extract": fake_extract, "resolve": fake_resolve, "judge": fake_judge,
                "agent": agent_script(), "reader": lambda m, t: "FINAL ANSWER: N4"}
    handlers.update(extra)
    return FakeLLM(handlers)


def make_cfg(tmp_path, **over):
    base = {"embed": {"backend": "hash", "cache_path": None},
            "llm": {"cache_path": None},
            "resolve": {"min_candidate_sim": 0.99},
            "eval": {"graphs_dir": str(tmp_path / "graphs"), "runs_dir": str(tmp_path / "runs"),
                     "splits_dir": str(tmp_path / "splits"),
                     "dataset_path": str(tmp_path / "lme.json"), "workers": 1}}
    for k, v in over.items():
        base.setdefault(k, {}).update(v)
    return load_config(overrides=base)


def make_embedder():
    return HashEmbedder()
