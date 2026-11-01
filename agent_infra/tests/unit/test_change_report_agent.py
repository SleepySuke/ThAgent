"""change_report_agent 三件套：wiring + policy + prompt 教学（矩阵 #6）。"""
from agents.change_report_agent.agent import build_agent
from harness.contract import RunContext
from harness.policy import NODE_POLICIES
from harness.sandbox.manager import SandboxManager
from harness.sandbox.worktree import WorktreeProvider


def _agent():
    run = RunContext(trace_id="t", repo_path="x", commit="defect-1",
                     event_sink=lambda e, p: None)
    mgr = SandboxManager(WorktreeProvider(allowed_cmds=frozenset()), "runs")
    return build_agent(run, mgr, NODE_POLICIES["change_report_agent"])


def test_build_change_report_wires_readonly():
    agent = _agent()
    assert agent.name == "change_report_agent"
    assert {t.__name__ for t in agent.tools} == {"read_artifact"}   # 只读面
    assert NODE_POLICIES["change_report_agent"].max_turns >= 15


def test_prompt_teaches_honest_no_recall():     # 矩阵 #6
    text = _agent().instruction
    assert "无既有用例可复用" in text and "全部建议新增" in text
    assert "test_recall.json" in text          # 读召回全文
    assert "recalled_n" in text and "risk_n" in text
    assert "不要因此报错" in text               # 缺上游键不拒产出
