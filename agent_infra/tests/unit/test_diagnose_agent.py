"""diagnose_agent 做实：wiring + prompt 教学（矩阵 #7）。"""
from agents.diagnose_agent.agent import build_agent
from harness.contract import RunContext
from harness.policy import NODE_POLICIES
from harness.sandbox.manager import SandboxManager
from harness.sandbox.worktree import WorktreeProvider


def _agent():
    run = RunContext(trace_id="t", repo_path="x", commit="defect-1",
                     event_sink=lambda e, p: None)
    mgr = SandboxManager(WorktreeProvider(allowed_cmds=frozenset()), "runs")
    return build_agent(run, mgr, NODE_POLICIES["diagnose_agent"])


def test_build_diagnose_wires_readonly():
    agent = _agent()
    assert agent.name == "diagnose_agent"
    assert {t.__name__ for t in agent.tools} == {"read_artifact"}
    assert NODE_POLICIES["diagnose_agent"].max_turns >= 15


def test_prompt_teaches_no_failure_honesty():   # 矩阵 #7
    text = _agent().instruction
    assert "root_causes=[]" in text                     # 全过输出空数组
    assert "无失败用例" in text and "不要为了产出而编造根因" in text
    assert "exit_code" in text and "stdout" in text      # 失败 stdout 消费
    assert "cr_report.json" in text                      # 风险对照
