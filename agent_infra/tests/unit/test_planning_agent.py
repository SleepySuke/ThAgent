from agents.planning_agent.agent import build_agent
from harness.contract import RunContext
from harness.policy import NODE_POLICIES
from harness.sandbox.manager import SandboxManager
from harness.sandbox.worktree import WorktreeProvider


def _agent():
    run = RunContext(trace_id="t", repo_path="x", commit="defect-1",
                     event_sink=lambda e, p: None)
    mgr = SandboxManager(WorktreeProvider(allowed_cmds=frozenset()), "runs")
    return build_agent(run, mgr, NODE_POLICIES["planning_agent"])


def test_build_planning_agent():
    agent = _agent()
    assert agent.name == "planning_agent"
    assert agent.model is not None
    for cb in ("before_agent_callback", "after_agent_callback",
               "before_model_callback", "after_model_callback"):
        assert callable(getattr(agent, cb))
    # 纯规划节点：唯一工具是 request_human（可问人，仍不接触沙箱）
    assert [getattr(t, "__name__", "") for t in agent.tools] == ["request_human"]


def test_plan_prompt_mentions_registry():
    # 断言组装后的 instruction 引导只选 registry 内节点（不直接读 prompt 文件）
    agent = _agent()
    for node in ("cr_agent", "test_recall_agent", "case_agent",
                 "script_agent", "case_executor", "report_agent"):
        assert node in agent.instruction
    assert "request_human" in agent.instruction  # HITL 使用指引（Task 6）
