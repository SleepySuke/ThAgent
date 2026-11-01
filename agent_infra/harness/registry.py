"""L 层：死 DAG 注册表（能力全集）。

节点两类：agent 节点（A2A 调用）与 program 节点（Harness 本地确定性执行）。
Planning agent 只能从 DAG 里选子集产出 ExecutionPlan，不能编出 DAG 不存在的
节点或依赖。依赖边即执行顺序约束（cr → test_recall → case → script →
case_executor；八期 V1 一次性链路切换，testing_agent 退役）。

# ponytail: 端口硬编码是刻意的——一进程一 agent 固定端口，服务发现/负载均衡
# 是生产才需要的东西，registry 的 url 字段就是未来挂发现机制的接缝。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AGENT_REGISTRY: dict[str, dict] = {
    # 真实现
    "planning_agent": {"type": "agent", "url": "http://127.0.0.1:8103"},
    "cr_agent": {"type": "agent", "url": "http://127.0.0.1:8101"},
    "requirement_agent": {"type": "agent", "url": "http://127.0.0.1:8104"},
    "strategy_agent": {"type": "agent", "url": "http://127.0.0.1:8105"},
    "case_agent": {"type": "agent", "url": "http://127.0.0.1:8106"},
    "script_agent": {"type": "agent", "url": "http://127.0.0.1:8107"},
    "diagnose_agent": {"type": "agent", "url": "http://127.0.0.1:8108"},
    "report_agent": {"type": "agent", "url": "http://127.0.0.1:8109"},
    # 测试召回（八期）：CR 风险 → 既有用例检索（recalled/gaps 契约）
    "test_recall_agent": {"type": "agent", "url": "http://127.0.0.1:8110"},
    # 变更分析报告（八期）：cr+test_recall 结论 → change_report.md（该测什么）
    "change_report_agent": {"type": "agent", "url": "http://127.0.0.1:8111"},
    # Program 节点（确定性，非 LLM）
    "case_executor": {"type": "program", "handler": "execute_cases"},
}

# 依赖边（八期新链：cr → test_recall → case → script → case_executor；
# requirement → strategy 前置语义链；case_executor → diagnose → report 收口）
DAG_EDGES: list[tuple[str, str]] = [
    ("requirement_agent", "strategy_agent"),
    ("strategy_agent", "cr_agent"),
    ("cr_agent", "test_recall_agent"),
    ("test_recall_agent", "change_report_agent"),   # T5 新增
    ("change_report_agent", "case_agent"),          # T5 新增（推荐是用例设计输入）
    ("test_recall_agent", "case_agent"),
    ("case_agent", "script_agent"),
    ("script_agent", "case_executor"),
    ("case_executor", "diagnose_agent"),
    ("diagnose_agent", "report_agent"),
    ("case_executor", "report_agent"),
]


@dataclass(frozen=True)
class NodeSpec:
    node_id: str
    type: Literal["agent", "program"]
    url: str = ""
    handler: str = ""


def resolve_node(node_id: str) -> NodeSpec:
    """查注册表，未知节点抛 KeyError（配置错误，早暴露）。"""
    spec = AGENT_REGISTRY[node_id]
    return NodeSpec(node_id=node_id, type=spec["type"],
                    url=spec.get("url", ""), handler=spec.get("handler", ""))


def successors(node_id: str) -> list[str]:
    return [b for a, b in DAG_EDGES if a == node_id]


def is_valid_edge(a: str, b: str) -> bool:
    return (a, b) in DAG_EDGES
