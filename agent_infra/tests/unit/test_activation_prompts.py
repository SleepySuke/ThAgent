"""六期 prompt 接线：planning 可选新链 + cr 消费 upstream + 序列化（矩阵 #12）。"""
import json
from pathlib import Path

from agent_server import render_prompt
from agents.planning_agent.agent import build_agent as build_planning
from harness.contract import AgentInput, RunContext
from harness.policy import NODE_POLICIES
from harness.sandbox.manager import SandboxManager
from harness.sandbox.worktree import WorktreeProvider

ROOT = Path(__file__).resolve().parents[2]


def _planning():
    run = RunContext(trace_id="t", repo_path="x", commit="d",
                     event_sink=lambda e, p: None)
    mgr = SandboxManager(WorktreeProvider(allowed_cmds=frozenset()), "runs")
    return build_planning(run, mgr, NODE_POLICIES["planning_agent"])


def test_planning_prompt_offers_full_chain():
    agent = _planning()
    for node in ("requirement_agent", "strategy_agent", "report_agent"):
        assert node in agent.instruction       # 做实节点进可选集
    assert "context_note" in agent.instruction  # 选链指引（带需求备注 → 全链）
    assert "严禁跳级" in agent.instruction       # 矩阵 #3 的 prompt 面


def test_planning_prompt_keeps_core_contract():
    agent = _planning()
    for node in ("cr_agent", "test_recall_agent", "case_agent",
                 "script_agent", "case_executor", "report_agent"):
        assert node in agent.instruction       # 新链可选集（八期 V1）
    assert "request_human" in agent.instruction
    assert "diagnose_agent" in agent.instruction  # defer 节点显式「不选」


def test_cr_prompt_teaches_upstream_usage():
    prompt = (ROOT / "agents" / "cr_agent" / "prompt.md").read_text(
        encoding="utf-8")
    assert "upstream" in prompt
    assert "requirement_agent" in prompt and "strategy_agent" in prompt
    assert "acceptance" in prompt               # 验收基准语义
    assert "缺失" in prompt or "为空" in prompt   # 缺失容忍


def test_upstream_serializes_into_prompt():  # 矩阵 #12
    ai = AgentInput(run_id="t", node_id="cr_agent", input_data={"commit": "d"},
                    upstream={"requirement_agent": {"task_type": "bugfix"},
                              "strategy_agent": {"focus_files": ["a.py"]}})
    rendered = render_prompt(ai.to_json())
    data = json.loads(rendered[rendered.index("{"):])   # 剥掉引导语
    assert data["upstream"] == {"requirement_agent": {"task_type": "bugfix"},
                                "strategy_agent": {"focus_files": ["a.py"]}}
