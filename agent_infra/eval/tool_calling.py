"""V 层：Tool Calling 评测——trace 事件 → 工具维度指标（纯离线，零 LLM）。

四指标（设计 §0）：legality（合法调用率）/ denied（越权拒绝数，只计
before_tool）/ must_use_hit（必用工具触达率）/ turns_per_node（轮次效率）。

节点归属：tool_call/policy_deny/llm_call 事件的 node_id 为 null（engine
_send 按名透传不带 node_id），按事件流顺序在 node_start/node_end 之间分段
归属；node_start payload 的 agent 字段（七期 Task 1）是权威，旧 trace 回退
到 plan_ready 的 {局部 id: registry agent} 映射，再退回 node_id 本身。
"""
from __future__ import annotations

import json
from pathlib import Path


def load_trace(run_dir: Path) -> list[dict]:
    """读 run 目录的 trace.jsonl → 事件列表（文件行序即时间序）。

    空行/JSON 损坏半行跳过不炸（矩阵 #1 容错面）；文件缺失抛
    FileNotFoundError——调用方必须响亮报错，绝不静默当空 run 计 0 分。
    """
    f = Path(run_dir) / "trace.jsonl"
    if not f.exists():
        raise FileNotFoundError(f"trace missing: {f}（run 未产出，不能静默 0 分）")
    events: list[dict] = []
    for line in f.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue  # 半行容错（矩阵 #1）
    return events


def _plan_agent_map(events: list[dict]) -> dict[str, str]:
    """旧 trace 兜底：plan_ready payload 的 {局部 id: registry agent} 映射。"""
    for e in events:
        if e.get("event") == "plan_ready":
            return {n["id"]: n["agent"] for n in e.get("payload", {}).get("nodes", [])
                    if n.get("id") and n.get("agent")}
    return {}


def score_tool_calling(events: list[dict], must_use: dict[str, list[str]]) -> dict:
    """单 run 工具维度打分（纯函数：事件列表 + golden must_use → 指标 dict）。"""
    plan_map = _plan_agent_map(events)
    called_tools: dict[str, set[str]] = {}
    turns: dict[str, int] = {}
    denied = 0
    total_calls = 0
    current: str | None = None
    saw_call = False  # 本段是否有过真实调用尝试
    for e in events:
        ev, payload = e.get("event"), e.get("payload", {})
        if ev == "node_start":
            current = (payload.get("agent") or plan_map.get(e.get("node_id"))
                       or e.get("node_id"))
            saw_call = False
        elif ev == "node_end":
            current = None
        elif ev == "tool_call" and current:
            total_calls += 1
            saw_call = True
            called_tools.setdefault(current, set()).add(payload.get("tool"))
        elif ev == "llm_call" and current:
            turns[current] = turns.get(current, 0) + 1
        elif (ev == "policy_deny" and payload.get("where") == "before_tool"
              and current):
            # 矩阵 #2：turn budget（before_model）不计入；且 deny 只在段内
            # 有过 tool_call 尝试时计（engine 先发 tool_call 再判定，
            # 孤儿 deny 是残缺 trace，不算幻觉——矩阵 #3 的 0 调用面）
            if saw_call:
                denied += 1
    entries = [(agent, tool) for agent, tools in must_use.items()
               for tool in tools]
    hits = sum(1 for agent, tool in entries
               if tool in called_tools.get(agent, ()))
    return {"legality": (total_calls - denied) / total_calls if total_calls else 1.0,
            "denied": denied,
            "must_use_hit": hits / len(entries) if entries else 1.0,
            "turns_per_node": turns,
            "tool_calls": total_calls}
