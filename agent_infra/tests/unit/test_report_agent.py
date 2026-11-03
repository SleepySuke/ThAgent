"""report 做实：只读 artifact 工具面 + policy + 契约（summary/verdicts/markdown）。"""
import json

import pytest

from agent_server import _parse_report, load_agent_by_name
from agents.report_agent.agent import build_agent
from harness.contract import OutputContractError, RunContext
from harness.policy import NODE_POLICIES
from harness.sandbox.manager import SandboxManager
from harness.sandbox.worktree import WorktreeProvider

REPORT = {"summary": "整体可控",
          "verdicts": [{"node": "cr_agent", "verdict": "request_changes"}],
          "stats": {"issues": 1}, "markdown": "# 审查报告\n正文。"}


def _agent():
    run = RunContext(trace_id="t", repo_path="x", commit="defect-1",
                     event_sink=lambda e, p: None)
    mgr = SandboxManager(WorktreeProvider(allowed_cmds=frozenset()), "runs")
    return build_agent(run, mgr, NODE_POLICIES["report_agent"])


def test_build_report_agent_reads_artifacts_only():
    agent = _agent()
    assert agent.name == "report_agent"
    assert {t.__name__ for t in agent.tools} == {"read_artifact", "search_knowledge"}
    for cb in ("before_agent_callback", "after_agent_callback",
               "before_model_callback", "after_model_callback",
               "before_tool_callback", "after_tool_callback"):
        assert callable(getattr(agent, cb))


def test_report_policy_readonly_and_memory_off():
    p = NODE_POLICIES["report_agent"]
    assert p.allowed_tools == frozenset({"read_artifact", "search_knowledge"})
    assert p.allowed_cmds == frozenset()
    assert p.memory_enabled is False


def test_report_prompt_mentions_upstream_and_tolerance():  # 矩阵 #11 prompt 面
    agent = _agent()
    assert "upstream" in agent.instruction
    assert "read_artifact" in agent.instruction
    assert "cr_report.json" in agent.instruction
    assert "缺失" in agent.instruction                  # 缺哪段就略过哪段


def test_parse_report_validates_contract():
    assert _parse_report(json.dumps(REPORT)) == REPORT  # 合法全量通过
    assert _parse_report(json.dumps(
        {k: v for k, v in REPORT.items() if k != "stats"}))["stats"] == {}
    for bad in ({"summary": "", "verdicts": [], "markdown": "x"},
                {"summary": "s", "verdicts": "no", "markdown": "x"},
                {"summary": "s", "verdicts": [], "markdown": "  "}):
        with pytest.raises(OutputContractError):
            _parse_report(json.dumps(bad))


def test_report_finalize_registered():
    spec = load_agent_by_name("report_agent")
    assert spec.artifact_name == "execution_report.md"  # 带扩展名 → md 落盘
    assert spec.validate is not None and spec.repair_prompt


def test_report_still_readonly_wired():
    agent = _agent()
    assert agent.name == "report_agent"
    assert {t.__name__ for t in agent.tools} == {"read_artifact", "search_knowledge"}   # 工具面不变


def test_prompt_teaches_execution_report():     # 矩阵 #8 教学钉桩
    text = _agent().instruction
    assert "执行报告" in text and "pass_rate" in text
    assert "未选入 diagnose" in text                  # 失败无根因时如实标注
    assert "diagnose_agent" in text and "test_recall_agent" in text
    assert "root_causes" in text


def test_report_prompt_teaches_exemplar_lookup():   # V2c-1 拉通道教学
    text = _agent().instruction
    assert "search_knowledge" in text and "范例" in text   # 产出前先检索认可范例
    assert "不抄" in text                                  # 回音室防线：不抄内容
