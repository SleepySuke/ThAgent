"""集成测试：engine 在规划完成/节点执行前/节点完成/失败四个时机打 checkpoint。"""
import json

from harness.contract import AgentOutput
from harness.engine import DEFAULT_PLAN, HarnessEngine


class _FakeEngine(HarnessEngine):
    def __init__(self, runs_root, output):
        super().__init__("http://127.0.0.1:1", runs_root)
        self._output = output
        self.sent = []

    async def _send(self, node_url, agent_input, tracer, task_id_box=None,
                    budget=None):
        self.sent.append(agent_input)
        return self._output


async def test_checkpoint_emitted_on_boundaries(tmp_path):
    out = AgentOutput(output_data={"issues": []}, artifact_url="", status="ok")
    engine = _FakeEngine(tmp_path / "runs", out)
    await engine.execute_for("t", {"repo": "x", "commit": "d"}, DEFAULT_PLAN)
    trace = [json.loads(line) for line in
             (tmp_path / "runs" / "t" / "trace.jsonl").read_text().splitlines()]
    assert any(e["event"] == "checkpoint" for e in trace)
    assert (tmp_path / "runs" / "t" / "checkpoint.json").exists()
    # 幂等键随 task 下发（首 attempt 格式 run_id:node_id:1）
    assert any(i.idempotency_key == "t:cr_agent:1" for i in engine.sent)
