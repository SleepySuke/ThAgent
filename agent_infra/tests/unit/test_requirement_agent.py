"""requirement 做实：只读工具面 + policy + 契约 prompt + server 注册。"""
from agent_server import load_agent_by_name
from agents.requirement_agent.agent import build_agent
from harness.contract import RunContext
from harness.policy import NODE_POLICIES
from harness.sandbox.manager import SandboxManager
from harness.sandbox.worktree import WorktreeProvider


def _agent():
    run = RunContext(trace_id="t", repo_path="x", commit="defect-1",
                     event_sink=lambda e, p: None)
    mgr = SandboxManager(WorktreeProvider(allowed_cmds=frozenset()), "runs")
    return build_agent(run, mgr, NODE_POLICIES["requirement_agent"])


def test_build_requirement_agent_wires_readonly_tools():
    agent = _agent()
    assert agent.name == "requirement_agent"
    # 只读工具面（build_tools 组装，内层函数名==工具名==白名单，坑 #17 天然满足）
    assert {t.__name__ for t in agent.tools} == {
        "read_diff", "read_file", "list_files"}
    for cb in ("before_agent_callback", "after_agent_callback",
               "before_model_callback", "after_model_callback",
               "before_tool_callback", "after_tool_callback"):
        assert callable(getattr(agent, cb))


def test_requirement_policy_readonly_and_memory_off():
    p = NODE_POLICIES["requirement_agent"]
    # 九期 MCP：+get_pr（opt-in 挂载，白名单常驻——坑 #16 G 层同步）
    assert p.allowed_tools == frozenset(
        {"read_diff", "read_file", "list_files", "get_pr"})
    assert p.allowed_cmds == frozenset()            # 无命令执行
    assert p.memory_enabled is False                # memory 关闭（设计 §1 G 行）


def test_requirement_prompt_contract():
    agent = _agent()
    for key in ("task_type", "scope", "risks", "acceptance"):
        assert key in agent.instruction              # 契约四件套进 prompt
    assert "read_diff" in agent.instruction
    assert "context_note" in agent.instruction       # 需求备注输入源


def test_requirement_finalize_registered():
    spec = load_agent_by_name("requirement_agent")
    assert spec.artifact_name == "requirement_brief"
    assert spec.validate is not None and spec.repair_prompt  # V3：按自身契约修复
