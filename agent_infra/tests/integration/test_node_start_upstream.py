"""集成：node_start payload 持久化 upstream（已截断）与 agent 引用（七期地基）。

覆盖矩阵 #10（体积界）与「这个节点看到了什么」的语义钉桩；_CaptureEngine
覆写 _send 绕过真实 A2A。
"""
import json

from harness.contract import AgentOutput, ExecutionPlan
from harness.engine import UPSTREAM_MAX_CHARS, HarnessEngine

CR_OUT = AgentOutput(output_data={"verdict": "approve", "issues": []},
                     artifact_url="", status="ok")
TEST_OUT = AgentOutput(output_data={"cases": 2}, artifact_url="", status="ok")
CHAIN = ExecutionPlan(
    plan_id="p", nodes=[{"id": "cr", "agent": "cr_agent"},
                        {"id": "script", "agent": "script_agent"}],
    edges=[["cr", "script"]])


class _CaptureEngine(HarnessEngine):
    def __init__(self, runs_root, outputs):
        super().__init__("http://127.0.0.1:1", runs_root)
        self._outputs = outputs

    async def _send(self, node_url, agent_input, tracer, task_id_box=None,
                    budget=None):
        return self._outputs[agent_input.node_id]


def _starts(runs, trace_id):
    return [e for e in (json.loads(ln) for ln in
                        (runs / trace_id / "trace.jsonl").read_text().splitlines())
            if e["event"] == "node_start"]


async def test_node_start_persists_agent_and_upstream(tmp_path):
    runs = tmp_path / "runs"
    eng = _CaptureEngine(runs, {"cr_agent": CR_OUT, "script_agent": TEST_OUT})
    await eng.execute_for("t-ns1", {"repo": "x", "commit": "d"}, CHAIN)
    starts = _starts(runs, "t-ns1")
    assert starts[0]["payload"] == {"agent": "cr_agent", "upstream": {}}
    assert starts[1]["payload"] == {
        "agent": "script_agent",
        "upstream": {"cr_agent": CR_OUT.output_data}}


async def test_program_node_start_has_empty_upstream(tmp_path, monkeypatch):
    from harness import programs
    runs = tmp_path / "runs"

    def _fake_handler(runs_root, run_id, artifact_refs):
        return {"exit_code": 0}

    monkeypatch.setitem(programs.PROGRAM_HANDLERS, "execute_cases",
                        _fake_handler)
    plan = ExecutionPlan(
        plan_id="p2", nodes=[{"id": "cr", "agent": "cr_agent"},
                             {"id": "exec", "program": "case_executor"}],
        edges=[["cr", "exec"]])
    eng = _CaptureEngine(runs, {"cr_agent": CR_OUT})
    await eng.execute_for("t-ns2", {"repo": "x", "commit": "d"}, plan)
    exec_start = _starts(runs, "t-ns2")[1]
    assert exec_start["payload"]["agent"] == "case_executor"
    assert exec_start["payload"]["upstream"] == {}   # program 节点不消费 upstream


async def test_node_start_upstream_clipped_and_bounded(tmp_path):  # 矩阵 #10
    runs = tmp_path / "runs"
    long_out = AgentOutput(output_data={"summary": "甲" * 900},
                           artifact_url="", status="ok")
    eng = _CaptureEngine(runs, {"cr_agent": long_out,
                                "script_agent": TEST_OUT})
    await eng.execute_for("t-ns3", {"repo": "x", "commit": "d"}, CHAIN)
    script_up = _starts(runs, "t-ns3")[1]["payload"]["upstream"]
    assert script_up["cr_agent"]["_truncated"] is True
    assert len(script_up["cr_agent"]["head"]) == UPSTREAM_MAX_CHARS
    for start in _starts(runs, "t-ns3"):   # 每值 ≤ 截断预算 + 包装开销
        for value in start["payload"]["upstream"].values():
            assert len(json.dumps(value, ensure_ascii=False)) <= UPSTREAM_MAX_CHARS + 40
