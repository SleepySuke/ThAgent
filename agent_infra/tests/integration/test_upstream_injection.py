"""集成：engine 把上游 output_data 注入下游 AgentInput.upstream。

覆盖矩阵 #1（node_end 截断标注）/#4（checkpoint 坏条目守卫）/#5（恢复降级）/
#7（DEFAULT_PLAN 向后兼容）。_FakeEngine 覆写 _send 绕过真实 A2A。
"""
import json

from harness.checkpoint import save_checkpoint
from harness.contract import AgentOutput, ExecutionPlan
from harness.engine import HarnessEngine

CR_OUT = AgentOutput(
    output_data={"verdict": "request_changes", "issues": []}, artifact_url="",
    status="ok", artifacts=[{"artifact_id": "A001", "type": "cr_report",
                             "uri": "runs/x/artifacts/cr_report.json"}])
TEST_OUT = AgentOutput(output_data={"cases": 2}, artifact_url="", status="ok")
CHAIN = ExecutionPlan(
    plan_id="p", nodes=[{"id": "cr", "agent": "cr_agent"},
                        {"id": "script", "agent": "script_agent"}],
    edges=[["cr", "script"]])


class _CaptureEngine(HarnessEngine):
    def __init__(self, runs_root, outputs):
        super().__init__("http://127.0.0.1:1", runs_root)
        self._outputs = outputs
        self.sent = []

    async def _send(self, node_url, agent_input, tracer, task_id_box=None,
                    budget=None):
        self.sent.append(agent_input)
        return self._outputs[agent_input.node_id]


def _trace_events(runs, trace_id):
    return [json.loads(ln) for ln in
            (runs / trace_id / "trace.jsonl").read_text().splitlines()]


async def test_upstream_injected_into_downstream(tmp_path):  # 矩阵 #7/#8 前置
    eng = _CaptureEngine(tmp_path / "runs",
                         {"cr_agent": CR_OUT, "script_agent": TEST_OUT})
    await eng.execute_for("t-inj", {"repo": "x", "commit": "d"}, CHAIN)
    assert eng.sent[0].upstream == {}              # 首节点无上游（默认空）
    assert eng.sent[1].upstream == {"cr_agent": CR_OUT.output_data}


async def test_node_end_reports_upstream_truncation(tmp_path):  # 矩阵 #1
    long_out = AgentOutput(
        output_data={"summary": "甲" * 900}, artifact_url="", status="ok")
    eng = _CaptureEngine(tmp_path / "runs",
                         {"cr_agent": long_out, "script_agent": TEST_OUT})
    await eng.execute_for("t-trunc", {"repo": "x", "commit": "d"}, CHAIN)
    node_ends = [e["payload"] for e in _trace_events(tmp_path / "runs", "t-trunc")
                 if e["event"] == "node_end"]
    script_end = next(p for p in node_ends if p.get("upstream_nodes"))
    assert script_end["upstream_nodes"] == ["cr_agent"]
    assert script_end["upstream_truncated"] is True
    assert eng.sent[1].upstream["cr_agent"]["_truncated"] is True


async def test_checkpoint_corrupt_entries_guarded(tmp_path):  # 矩阵 #4
    runs = tmp_path / "runs"
    save_checkpoint(runs, "t-corrupt", {
        "run_id": "t-corrupt", "context_id": "t-corrupt", "current_node": None,
        "harness_state": "executing", "completed_nodes": ["cr"],
        "node_outputs": {"cr": "结构损坏"}, "version": 1, "created_at": 0.0})
    eng = _CaptureEngine(runs, {"script_agent": TEST_OUT})
    await eng.execute_for("t-corrupt", {"repo": "x", "commit": "d"}, CHAIN)
    assert eng.sent[0].upstream == {}              # 坏条目跳过，run 不炸
    assert any(e["event"] == "upstream_corrupt"
               and e["payload"]["skipped"] == 1
               for e in _trace_events(runs, "t-corrupt"))


async def test_trace_inference_degrades_to_recovered(tmp_path):  # 矩阵 #5
    runs = tmp_path / "runs"
    tr_dir = runs / "t-rec"
    tr_dir.mkdir(parents=True)
    (tr_dir / "trace.jsonl").write_text(
        json.dumps({"event": "node_end", "node_id": "cr",
                    "payload": {"status": "ok"}}) + "\n", encoding="utf-8")
    (tr_dir / "checkpoint.json").write_text("{corrupted", encoding="utf-8")
    eng = _CaptureEngine(runs, {"script_agent": TEST_OUT})
    await eng.execute_for("t-rec", {"repo": "x", "commit": "d"}, CHAIN)
    assert eng.sent[0].upstream == {"cr_agent": {"recovered": True}}
