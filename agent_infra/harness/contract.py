"""C 层：AgentInput/AgentOutput 契约、ExecutionPlan 解析与输出校验。

多 agent 数据流：上游 AgentOutput.artifacts → 下游 AgentInput.artifact_refs
（artifact 引用，不塞大段文本）。Planning agent 产出 ExecutionPlan，节点与
依赖必须落在死 DAG（harness/registry.py）内。
"""
from __future__ import annotations

import dataclasses
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

VALID_SEVERITY = {"high", "mid", "low"}
VALID_TYPE = {"bug", "consistency", "maintainability", "exception"}
VALID_VERDICT = {"approve", "request_changes"}


class OutputContractError(ValueError):
    """agent 输出不满足契约。"""


@dataclass
class AgentInput:
    run_id: str                  # 全局 Harness Run ID（trace_id）
    node_id: str                 # 当前节点
    input_data: dict = field(default_factory=dict)  # 节点输入（一期 payload）
    context_id: str = ""         # 多轮上下文标识（单 run 内等于 run_id）
    task_id: str = ""            # A2A Task ID（server 侧回填，幂等用）
    artifact_refs: list = field(default_factory=list)  # 上游产物引用
    history: list = field(default_factory=list)        # 必要历史（一期 context）
    hitl_feedback: dict | None = None                  # 人工回填（一期 feedback）
    upstream: dict = field(default_factory=dict)       # 上游语义结论 {registry 名: output_data}
    idempotency_key: str = ""    # run_id:node_id:attempt（重试幂等，随 task 下发）
    attempt: int = 1             # 节点尝试轮次（engine 每次尝试前设置，矩阵 #16）

    def to_json(self) -> str:
        return json.dumps(dataclasses.asdict(self), ensure_ascii=False)


@dataclass
class AgentOutput:
    output_data: dict
    artifact_url: str
    status: Literal["ok", "failed", "timeout"]
    artifacts: list = field(default_factory=list)  # 下游引用位（一期只有 artifact_url）
    metrics: dict = field(default_factory=dict)
    next_hint: dict = field(default_factory=dict)  # agent 只给建议，不决定编排


@dataclass
class ExecutionPlan:
    plan_id: str
    nodes: list[dict]         # [{"id": "cr", "agent": "cr_agent"}, ...]
    edges: list[list[str]]    # [["cr", "testing"], ...]（局部 id 之间的依赖）


@dataclass
class RunContext:
    """工具与三层 callback 共享的运行上下文（agent 进程内）。

    只保留 ADK 没有的东西：跨进程身份（trace_id/repo/commit，经 A2A 传入）
    与事件汇（回传 harness 的 trace）。轮次计数走 ADK session state，
    不在这里自造（见 harness/callbacks.py）。
    """
    trace_id: str
    repo_path: str
    commit: str
    artifacts_dir: str = ""  # 本 run 的 artifacts 目录（read_artifact 用）
    node_id: str = ""          # 当前节点（A2A server 侧回填，session 寻回用）
    attempt: int = 1           # 节点尝试轮次（重试轮工具首调用前 reset 沙箱，矩阵 #16）
    event_sink: Callable[[str, dict], None] = field(
        default_factory=lambda: lambda event, payload: None)


def validate_output(data: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["output is not a json object"]
    issues = data.get("issues")
    if not isinstance(issues, list):
        errors.append("issues must be a list")
    else:
        for i, it in enumerate(issues):
            required = {"file", "line", "severity", "type", "desc"}
            if not isinstance(it, dict) or not required <= set(it):
                errors.append(f"issues[{i}] missing fields")
            elif it.get("severity") not in VALID_SEVERITY or it.get("type") not in VALID_TYPE:
                errors.append(f"issues[{i}] severity/type out of domain")
    if data.get("verdict") not in VALID_VERDICT:
        errors.append("verdict must be approve|request_changes")
    if not isinstance(data.get("summary"), str) or not data["summary"]:
        errors.append("summary must be a non-empty string")
    return errors


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def _extract_json(text: str) -> str:
    """取 fence 内 JSON（无 fence 则原样）。"""
    m = _FENCE_RE.search(text)
    return m.group(1).strip() if m else text


def parse_output(text: str) -> AgentOutput:
    """从 agent 最终回复提取契约 JSON。失败抛 OutputContractError。"""
    candidates: list[str] = [text]
    m = _FENCE_RE.search(text)
    if m:
        candidates.insert(0, m.group(1).strip())
    for cand in candidates:
        try:
            data = json.loads(cand)
        except json.JSONDecodeError:
            continue
        start = cand.find("{")
        end = cand.rfind("}")
        if not isinstance(data, dict) and 0 <= start < end:
            try:
                data = json.loads(cand[start:end + 1])
            except json.JSONDecodeError:
                continue
        errors = validate_output(data)
        if errors:
            raise OutputContractError("; ".join(errors))
        return AgentOutput(output_data=data, artifact_url="", status="ok")
    raise OutputContractError("no valid contract json in agent response")


def parse_result(text: str) -> AgentOutput:
    """解析 agent server 终态回传的包装 JSON（A2A 契约，engine 侧统一入口）。

    与 parse_output 的分工：parse_output 解析 agent 的最终回复文本（裸报告
    JSON，server 侧用）；parse_result 解析 server 包装后的
    {output_data, artifact_url, status}（harness engine 侧用）。
    非 JSON 或缺 output_data 时原文进异常消息，保证失败原因可观测。
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise OutputContractError(f"non-json terminal text: {text[:300]!r}") from e
    if not isinstance(data, dict) or "output_data" not in data:
        raise OutputContractError(f"terminal text missing output_data: {text[:300]!r}")
    return AgentOutput(output_data=data["output_data"],
                       artifact_url=data.get("artifact_url", ""),
                       status=data.get("status", "ok"),
                       artifacts=data.get("artifacts", []),
                       metrics=data.get("metrics", {}),
                       next_hint=data.get("next_hint", {}))


def _node_ref(node: dict) -> str:
    """节点 dict 里引用的 registry 名（agent 或 program 二选一）。"""
    return node.get("agent") or node.get("program") or ""


def parse_plan(text: str) -> ExecutionPlan:
    """解析 Planning agent 的 ExecutionPlan，校验节点/边合法。

    校验：每个节点的 agent/program 必须可 resolve（registry 内）；每条边两端
    局部 id 必须在本 plan 的 nodes 内，且映射到 registry 后是合法依赖边。
    违反任一条件抛 OutputContractError（plan 是编排契约的一部分）。
    """
    from harness.registry import is_valid_edge, resolve_node

    try:
        data = json.loads(_extract_json(text))
    except json.JSONDecodeError as e:
        raise OutputContractError(f"non-json plan: {text[:300]!r}") from e
    if not isinstance(data, dict):
        raise OutputContractError("plan is not a json object")
    nodes = data.get("nodes")
    edges = data.get("edges")
    if not isinstance(nodes, list) or not nodes:
        raise OutputContractError("plan.nodes must be a non-empty list")
    if not isinstance(edges, list):
        raise OutputContractError("plan.edges must be a list")

    by_id: dict[str, str] = {}
    for n in nodes:
        if not isinstance(n, dict) or "id" not in n:
            raise OutputContractError("each plan node needs an 'id'")
        ref = _node_ref(n)
        if not ref:
            raise OutputContractError(f"node {n.get('id')!r} missing agent/program")
        try:
            resolve_node(ref)  # 节点必须在 registry 里
        except KeyError:
            raise OutputContractError(f"plan references unknown node: {ref}") from None
        by_id[n["id"]] = ref

    for edge in edges:
        if (not isinstance(edge, list) or len(edge) != 2
                or edge[0] not in by_id or edge[1] not in by_id):
            raise OutputContractError(f"invalid edge: {edge!r}")
        if not is_valid_edge(by_id[edge[0]], by_id[edge[1]]):
            raise OutputContractError(
                f"edge not in DAG: {by_id[edge[0]]} -> {by_id[edge[1]]}")
    return ExecutionPlan(plan_id=data.get("plan_id", ""), nodes=nodes, edges=edges)
