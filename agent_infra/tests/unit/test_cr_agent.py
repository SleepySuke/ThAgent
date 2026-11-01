from pathlib import Path

import pytest

from agents.cr_agent.agent import AgentEvents, build_agent
from harness.contract import RunContext
from harness.policy import NODE_POLICIES, TurnBudgetExceeded
from harness.sandbox.manager import SandboxManager
from harness.sandbox.worktree import WorktreeProvider


class _Ctx:  # CallbackContext 极简替身（我们只用 name）
    def __init__(self):
        self.state = {}


class _Tool:
    def __init__(self, name):
        self.name = name


def _agent(events):
    run = RunContext(trace_id="t", repo_path="x", commit="defect-1",
                     event_sink=events.sink)
    mgr = SandboxManager(WorktreeProvider(allowed_cmds=frozenset()), "runs")
    return build_agent(run, mgr, NODE_POLICIES["cr_agent"])


def test_build_agent_wires_everything():
    events = AgentEvents()
    agent = _agent(events)
    assert agent.name == "cr_agent"
    for cb in ("before_agent_callback", "after_agent_callback",
               "before_model_callback", "after_model_callback",
               "before_tool_callback", "after_tool_callback"):
        assert callable(getattr(agent, cb))
    # CR 选 4 个沙箱工具 + request_human（HITL）+ search_knowledge（知识检索）
    # + SkillToolset（ADK 原生技能加载）
    assert len(agent.tools) == 7
    from google.adk.tools.skill_toolset import SkillToolset
    assert any(isinstance(t, SkillToolset) for t in agent.tools)
    # 内层函数名即工具名（ADK FunctionTool 靠 __name__ 标识），必须与白名单一致
    assert "request_human" in {getattr(t, "__name__", "") for t in agent.tools}
    assert "search_knowledge" in {getattr(t, "__name__", "") for t in agent.tools}


def test_callback_signatures_accept_adk_keyword_invocation():
    """ADK 按关键字调用 callback（callback_context=... 等）；
    参数名对不上会在运行期 TypeError——静态签名断言防回归。"""
    import inspect

    expected = {
        "before_agent_callback": {"callback_context"},
        "after_agent_callback": {"callback_context"},
        "before_model_callback": {"callback_context", "llm_request"},
        "after_model_callback": {"callback_context", "llm_response"},
        "before_tool_callback": {"tool", "args", "tool_context"},
        "after_tool_callback":
            {"tool", "args", "tool_context", "tool_response"},
    }
    events = AgentEvents()
    agent = _agent(events)
    for cb_name, params in expected.items():
        sig = inspect.signature(getattr(agent, cb_name))
        assert params <= set(sig.parameters), f"{cb_name} 缺关键字参数: {params}"


def test_before_tool_denies_and_emits():
    events = AgentEvents()
    agent = _agent(events)
    result = agent.before_tool_callback(
        tool=_Tool("run_cmd"), args={"cmd": ["curl", "x"]}, tool_context=None)
    assert result == {"error": "policy denied: command not allowed: curl"}
    assert events.has("policy_deny")


def test_before_model_enforces_turn_budget():
    events = AgentEvents()
    agent = _agent(events)
    policy = NODE_POLICIES["cr_agent"]
    with pytest.raises(TurnBudgetExceeded):
        ctx = _Ctx()  # 轮次计在 session state 里：同一 context 复用才累加
        for _ in range(policy.max_turns + 1):
            agent.before_model_callback(ctx, None)


def test_after_model_emits_usage_tolerant():
    events = AgentEvents()
    agent = _agent(events)

    class _Resp:  # usage_metadata 缺失也不崩
        usage_metadata = None

    agent.after_model_callback(_Ctx(), _Resp())
    assert events.has("llm_end")


def test_prompt_teaches_agent_to_use_history_conventions():
    prompt = (Path(__file__).resolve().parents[2] / "agents" / "cr_agent"
              / "prompt.md").read_text(encoding="utf-8")
    assert "team_convention" in prompt
    assert "history" in prompt
    assert "request_human" in prompt  # HITL 使用指引（Task 6）
    assert "knowledge" in prompt  # 知识注入段（Task 3）
    assert "search_knowledge" in prompt  # 知识检索指引（Task 4）
