"""E2E：SSE 事件顺序 + 打字机数据完整性（真实 A2A server + fake agent）。

跨进程真实链路：fake agent 在 server 线程里 event_sink 出 llm_delta / tool_call /
tool_result，经 A2A 流回 engine 落 trace——验证 delta 先于 node_end 到达且拼接
无损（SSE HTTP 层顺序已由 app 集成测试覆盖，此处只看 engine 侧真实链路）。
"""
from __future__ import annotations

import json

import pytest

from harness.engine import DEFAULT_PLAN, HarnessEngine
from tests.e2e.test_memory_ab import CANNED, _FakeServer, _free_port


@pytest.fixture
def stream_setup(tmp_path):
    runs = tmp_path / "runs"

    async def fake_run(run, prompt):
        run.event_sink("llm_delta", {"text": "思考片段A", "thought": True})
        run.event_sink("llm_delta", {"text": "，片段B", "thought": True})
        run.event_sink("tool_call", {"tool": "read_diff", "call_id": "c1"})
        run.event_sink("tool_result", {"tool": "read_diff", "call_id": "c1",
                                       "ok": True})
        return CANNED

    srv = _FakeServer(runs, fake_run, _free_port())
    srv.start()
    try:
        yield runs, srv
    finally:
        srv.stop()  # 断言失败也回收 server，不留监听线程


async def test_sse_order_and_delta_completeness(stream_setup):
    runs, srv = stream_setup

    engine = HarnessEngine(None, runs,
                           agent_urls={"cr_agent": f"http://127.0.0.1:{srv.port}"})
    await engine.execute_for("e2e-stream", {"repo": "x", "commit": "d"},
                             DEFAULT_PLAN)
    trace = [json.loads(line) for line in
             (runs / "e2e-stream" / "trace.jsonl").read_text(encoding="utf-8")
             .splitlines()]
    names = [e["event"] for e in trace]
    assert names.index("llm_delta") < names.index("node_end")
    deltas = [e for e in trace if e["event"] == "llm_delta"]
    joined = "".join(e["payload"]["text"] for e in deltas
                     if e["payload"].get("thought"))
    assert joined == "思考片段A，片段B"     # delta 拼接完整性（A2）
