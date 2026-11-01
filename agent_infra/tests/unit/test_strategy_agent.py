"""strategy 做实：只读工具面 + policy + 上游消费/缺失容忍的 prompt。"""
from agent_server import load_agent_by_name
from agents.strategy_agent.agent import build_agent
from harness.contract import RunContext
from harness.policy import NODE_POLICIES
from harness.sandbox.manager import SandboxManager
from harness.sandbox.worktree import WorktreeProvider


def _agent():
    run = RunContext(trace_id="t", repo_path="x", commit="defect-1",
                     event_sink=lambda e, p: None)
    mgr = SandboxManager(WorktreeProvider(allowed_cmds=frozenset()), "runs")
    return build_agent(run, mgr, NODE_POLICIES["strategy_agent"])


def test_build_strategy_agent_wires_readonly_tools():
    agent = _agent()
    assert agent.name == "strategy_agent"
    assert {t.__name__ for t in agent.tools} == {
        "read_diff", "read_file", "list_files"}
    for cb in ("before_agent_callback", "after_agent_callback",
               "before_model_callback", "after_model_callback",
               "before_tool_callback", "after_tool_callback"):
        assert callable(getattr(agent, cb))


def test_strategy_policy_readonly_and_memory_off():
    p = NODE_POLICIES["strategy_agent"]
    assert p.allowed_tools == frozenset(
        {"read_diff", "read_file", "list_files"})
    assert p.allowed_cmds == frozenset()
    assert p.memory_enabled is False


def test_strategy_prompt_consumes_upstream_with_tolerance():  # 矩阵 #2 prompt 面
    agent = _agent()
    assert "upstream" in agent.instruction
    assert "requirement_agent" in agent.instruction   # 上游键 = registry 名
    assert "缺失" in agent.instruction                 # 缺失容忍指引
    for key in ("focus_files", "check_order", "severity_hint"):
        assert key in agent.instruction


def test_strategy_finalize_registered():
    spec = load_agent_by_name("strategy_agent")
    assert spec.artifact_name == "review_strategy"
    assert spec.validate is not None and spec.repair_prompt  # V3 自动生效
