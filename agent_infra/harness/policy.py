"""G 层：声明式节点策略 + 判定函数。策略是数据，enforcement 在 callbacks。"""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


class PolicyViolation(RuntimeError):
    """policy 判定拒绝并需要中断 agent 时抛出。"""


class TurnBudgetExceeded(PolicyViolation):
    """轮次预算耗尽，强制截断。"""


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str


@dataclass(frozen=True)
class NodePolicy:
    allowed_tools: frozenset[str]
    allowed_cmds: frozenset[str]
    path_scope: str = "sandbox://"
    max_turns: int = 15
    timeout_s: int = 300
    max_total_cmds: int = 40
    memory_enabled: bool = False
    memory_kinds: frozenset[str] = frozenset()  # 默认空 = deny-by-default
    max_attempts: int = 3       # 节点级重试次数（含首次）
    backoff_s: float = 1.0      # 重试退避基数（指数：base * 2^(attempt-1)）


# 未显式配置节点的兜底（占位 agent / 新节点）：deny-by-default
DEFAULT_NODE_POLICY = NodePolicy(
    allowed_tools=frozenset(), allowed_cmds=frozenset(), path_scope="sandbox://",
    max_turns=10, timeout_s=120, max_total_cmds=0)


NODE_POLICIES: dict[str, NodePolicy] = {
    "cr_agent": NodePolicy(
        allowed_tools=frozenset(
            {"read_diff", "read_file", "list_files", "run_cmd",
             # HITL：关键信息缺失时向人提问（无超时等待，经 /internal/hitl resolve）
             "request_human",
             # 知识检索（RAG 拉通道）：规范详情/历史方案的运行时检索
             "search_knowledge",
             # ADK SkillToolset 暴露的技能加载工具（run_skill_script 刻意
             # 不放行：无脚本资源，治理面不开执行口）
             "list_skills", "load_skill", "load_skill_resource"}),
        allowed_cmds=frozenset(
            {"python", "pytest", "ruff", "pip", "ls", "cat", "grep", "git"}),
        path_scope="sandbox://",
        max_turns=15,
        timeout_s=300,
        max_total_cmds=40,
        memory_enabled=True,
        # knowledge：知识库摘录（RAG 推通道注入），随 team_convention/past_review 同门控
        memory_kinds=frozenset({"team_convention", "past_review", "knowledge"}),
    ),
    # 规划器不接触沙箱（纯规划，无命令）；唯一工具是向人提问（HITL）
    "planning_agent": NodePolicy(
        allowed_tools=frozenset({"request_human"}),
        allowed_cmds=frozenset(),
        path_scope="sandbox://",
        max_turns=10,
        timeout_s=120,
        max_total_cmds=0,
    ),
    # 脚本生成（八期做实，接管原 testing 职责）：读用例清单（read_artifact）+
    # 写测试脚本（write_file 唯一写入口）+ 自测（run_cmd）；testing_agent 退役
    "script_agent": NodePolicy(
        allowed_tools=frozenset(
            {"read_artifact", "read_file", "list_files", "write_file", "run_cmd"}),
        allowed_cmds=frozenset({"python", "pytest", "ls", "cat", "grep"}),
        # 六期教训沿袭：写脚本+跑用例是全链最重的活，20 轮
        max_turns=20,
        timeout_s=300,
        max_total_cmds=20,
    ),
    # 需求分析（六期做实）：只读工具子集——读 diff/文件/列表，无命令执行、
    # memory 关闭（默认值）——产出语义结论（requirement_brief），不亲自审查
    "requirement_agent": NodePolicy(
        allowed_tools=frozenset({"read_diff", "read_file", "list_files"}),
        allowed_cmds=frozenset(),
        # ponytail: 15 轮——MiMo 实测读 diff+多文件后 10 轮不够产 JSON（全链
        # 冒烟 turn budget exceeded 三连）；工具只读无滥用面，预算从宽
        max_turns=15,
        timeout_s=180,
        max_total_cmds=0,
    ),
    # 审查策略（六期做实）：只读工具子集，同 requirement——消费上游任务说明 +
    # diff，产出重点面/顺序/严重度提示（review_strategy），不亲自审查
    "strategy_agent": NodePolicy(
        allowed_tools=frozenset({"read_diff", "read_file", "list_files"}),
        allowed_cmds=frozenset(),
        # ponytail: 15 轮——upstream 注入后 MiMo 轮次消耗上移（冒烟 11>10 三连）
        max_turns=15,
        timeout_s=180,
        max_total_cmds=0,
    ),
    # 报告收口（六期做实）：只读 artifacts（read_artifact——汇总全链结论，
    # 读 worktree 之外的 cr_report.json 等），产出人读执行报告。
    # ponytail: 300s——聚合全链结论+修复轮实测 180s 不够（真实冒烟超时一次）
    "report_agent": NodePolicy(
        # V2c-1：+search_knowledge（exemplar 拉通道，裁定 10）——产出前检索
        # 认可范例参考组织结构（不抄内容，回音室防线）
        allowed_tools=frozenset({"read_artifact", "search_knowledge"}),
        allowed_cmds=frozenset(),
        # ponytail: 15 轮——同 strategy：upstream 注入后轮次上移，聚合+修复轮要余量
        max_turns=15,
        timeout_s=300,
        max_total_cmds=0,
    ),
    # 测试召回（八期）：query 构建+缺口判断是语义活，工具面只给知识检索（无沙箱
    # 无命令）；HITL 兜底（矩阵 #2：风险全空时向人确认测试意图）
    "test_recall_agent": NodePolicy(
        allowed_tools=frozenset({"search_knowledge", "request_human"}),
        allowed_cmds=frozenset(),
        max_turns=15,
        timeout_s=180,
        max_total_cmds=0,
    ),
    # 用例设计（八期做实）：消费 upstream（recalled/gaps/cr）设计用例清单；只读
    # 工具——read_artifact 读 cr_report/test_recall 全文，read_file/list_files 看
    # 被测模块签名；无命令执行，产物是 JSON 契约（server 落盘，无需 write_file）
    "case_agent": NodePolicy(
        # V2c-1：+search_knowledge（exemplar 拉通道，同 report）
        allowed_tools=frozenset(
            {"read_artifact", "read_file", "list_files", "search_knowledge"}),
        allowed_cmds=frozenset(),
        max_turns=15,
        # ponytail: 300s——读多文件+设计用例实测 180s 偶发超时（基线 d4 单点
        # 方差；六期 report 同款教训：聚合型 agent 要余量）
        timeout_s=300,
        max_total_cmds=0,
    ),
    # 变更分析报告（八期）：cr+test_recall 上游结论 → change_report.md（该测什么）；
    # 只读 artifacts，无命令，无 memory
    "change_report_agent": NodePolicy(
        allowed_tools=frozenset({"read_artifact"}),
        allowed_cmds=frozenset(),
        max_turns=15,
        timeout_s=300,
        max_total_cmds=0,
    ),
    # 失败诊断（八期做实）：消费 executor 失败 stdout（upstream）+ cr 风险对照，
    # 产出根因；只读 artifacts，无命令——按需触发（plan 选入），无失败空转
    "diagnose_agent": NodePolicy(
        allowed_tools=frozenset({"read_artifact"}),
        allowed_cmds=frozenset(),
        max_turns=15,
        timeout_s=180,
        max_total_cmds=0,
    ),
}


def check_run(policy: NodePolicy | None) -> PolicyDecision:
    if policy is None:
        return PolicyDecision(False, "no policy for this node")
    return PolicyDecision(True, "ok")


def check_turn(policy: NodePolicy, turn: int) -> PolicyDecision:
    if turn > policy.max_turns:
        return PolicyDecision(False, f"turn budget exceeded: {turn} > {policy.max_turns}")
    return PolicyDecision(True, "ok")


def check_tool(policy: NodePolicy, tool_name: str, args: dict[str, Any]) -> PolicyDecision:
    if tool_name not in policy.allowed_tools:
        return PolicyDecision(False, f"tool not allowed: {tool_name}")
    if tool_name == "run_cmd":
        cmd = args.get("cmd")
        if not isinstance(cmd, list) or not cmd or not all(isinstance(x, str) for x in cmd):
            return PolicyDecision(False, "run_cmd args['cmd'] must be a non-empty list[str]")
        head = os.path.basename(cmd[0])
        if head not in policy.allowed_cmds:
            return PolicyDecision(False, f"command not allowed: {head}")
    return PolicyDecision(True, "ok")
