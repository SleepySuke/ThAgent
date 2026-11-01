"""case_agent 做实：wiring + policy + prompt 教学。"""
from agents.case_agent.agent import build_agent
from harness.contract import RunContext
from harness.policy import NODE_POLICIES
from harness.sandbox.manager import SandboxManager
from harness.sandbox.worktree import WorktreeProvider


def _agent():
    run = RunContext(trace_id="t", repo_path="x", commit="defect-1",
                     event_sink=lambda e, p: None)
    mgr = SandboxManager(WorktreeProvider(allowed_cmds=frozenset()), "runs")
    return build_agent(run, mgr, NODE_POLICIES["case_agent"])


def test_build_case_agent_wires_readonly_tools():
    agent = _agent()
    assert agent.name == "case_agent"
    assert {t.__name__ for t in agent.tools} == {
        "read_artifact", "read_file", "list_files"}   # 只读面（坑 #17）
    assert NODE_POLICIES["case_agent"].max_turns >= 15


def test_prompt_teaches_reuse_generate_and_coverage():
    text = _agent().instruction
    assert '"reuse"' in text and '"generate"' in text     # 双动作域
    assert "read_artifact" in text and "cr_report.json" in text
    assert "不要因此报错" in text                          # 缺上游键不拒产出
    assert "src" in text and "linked_risk" in text         # 契约字段教学
    assert "TC-101" in text                                # 新编号起点教学
