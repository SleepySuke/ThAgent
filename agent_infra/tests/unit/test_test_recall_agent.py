"""test_recall_agent 三件套：wiring + prompt 教学（矩阵 #1/#2/#5 的 U 面）。"""
from agents.test_recall_agent.agent import build_agent
from harness.contract import RunContext
from harness.policy import NODE_POLICIES
from harness.sandbox.manager import SandboxManager
from harness.sandbox.worktree import WorktreeProvider


def _agent():
    run = RunContext(trace_id="t", repo_path="x", commit="defect-1",
                     event_sink=lambda e, p: None)
    mgr = SandboxManager(WorktreeProvider(allowed_cmds=frozenset()), "runs")
    return build_agent(run, mgr, NODE_POLICIES["test_recall_agent"])


def test_build_test_recall_wires_tools():
    agent = _agent()
    assert agent.name == "test_recall_agent"
    tool_names = {t.__name__ for t in agent.tools}
    assert tool_names == {"search_knowledge", "request_human"}   # 无沙箱工具（坑 #17）
    for cb in ("before_agent_callback", "after_agent_callback",
               "before_model_callback", "after_model_callback",
               "before_tool_callback", "after_tool_callback"):
        assert callable(getattr(agent, cb))


def test_policy_tight_toolface_and_turns():
    p = NODE_POLICIES["test_recall_agent"]
    assert set(p.allowed_tools) == {"search_knowledge", "request_human"}
    assert p.allowed_cmds == frozenset() and p.max_total_cmds == 0
    assert p.max_turns >= 15                      # 六期教训：预算从宽


def test_prompt_teaches_degradation_paths():     # 矩阵 #1/#2/#5 教学钉桩
    text = _agent().instruction
    assert "recalled=[]" in text and "gaps = 全量风险" in text   # #1 诚实降级
    assert "skipped" in text                                     # #2 空风险跳过
    assert "检索失败" in text and "不要因此拒绝产出" in text      # #5 工具错误降级
    assert "case_id" in text and "matched_risk" in text          # 契约字段教学
