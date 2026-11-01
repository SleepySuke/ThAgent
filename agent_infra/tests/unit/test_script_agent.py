"""script_agent 做实：wiring + prompt 教学（矩阵 #3 fallback 的 U 面）。"""
from agents.script_agent.agent import build_agent
from harness.contract import RunContext
from harness.policy import NODE_POLICIES
from harness.sandbox.manager import SandboxManager
from harness.sandbox.worktree import WorktreeProvider


def _agent():
    run = RunContext(trace_id="t", repo_path="x", commit="defect-1",
                     event_sink=lambda e, p: None)
    mgr = SandboxManager(WorktreeProvider(allowed_cmds=frozenset()), "runs")
    return build_agent(run, mgr, NODE_POLICIES["script_agent"])


def test_build_script_agent_wires_tools():
    agent = _agent()
    assert agent.name == "script_agent"
    tool_names = {t.__name__ for t in agent.tools}
    assert tool_names == {"read_artifact", "write_file", "read_file",
                          "list_files", "run_cmd"}     # 与 testing 同面（坑 #17）
    assert NODE_POLICIES["script_agent"].max_turns == 20   # 六期教训沿袭
    for cb in ("before_agent_callback", "after_agent_callback",
               "before_model_callback", "after_model_callback",
               "before_tool_callback", "after_tool_callback"):
        assert callable(getattr(agent, cb))


def test_script_prompt_teaches_case_list_and_fallback():
    text = _agent().instruction
    assert "case_list.json" in text and "read_artifact" in text
    assert "reuse" in text and "generate" in text
    assert "fallback→generate" in text                # 矩阵 #3 降级教学
    assert "id 必须出现在脚本文本" in text              # cover_ratio 的锚约定
    assert "test_cases.py" in text and "write_file" in text
