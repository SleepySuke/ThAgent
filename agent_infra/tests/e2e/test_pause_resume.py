"""E2E：打断（对真实 A2A 发 cancel）→ PAUSED → resume → run 完成。

fake_run 固定睡 0.4s：0.15s 处 pause 时 node 必然还在跑（不可能已完成），
pause_run 必真；resume 带 feedback 重发，经真实 A2A 再次到达 agent。
"""
from __future__ import annotations

import asyncio
import json

from harness.engine import DEFAULT_PLAN, HarnessEngine
from tests.e2e.test_memory_ab import CANNED, _FakeServer, _free_port


async def test_pause_resume_real_a2a(tmp_path):
    runs = tmp_path / "runs"
    gate = asyncio.Event()

    async def fake_run(run, prompt):
        if "hitl_feedback" in prompt:
            gate.set()                       # resume 重发带反馈
        await asyncio.sleep(0.4)             # 给 pause 留窗口
        return CANNED

    srv = _FakeServer(runs, fake_run, _free_port())
    srv.start()
    task: asyncio.Task | None = None
    try:
        engine = HarnessEngine(None, runs,
                               agent_urls={"cr_agent":
                                           f"http://127.0.0.1:{srv.port}"})
        task = asyncio.create_task(engine.execute_for(
            "e2e-pr", {"repo": "x", "commit": "d"}, DEFAULT_PLAN))
        await asyncio.sleep(0.15)
        assert await engine.pause_run("e2e-pr") is True
        await asyncio.sleep(0.1)
        assert engine.resume_run("e2e-pr", text="继续")
        await asyncio.wait_for(task, timeout=15)
        assert gate.is_set()                 # resume 的反馈确实到达 agent prompt
        trace = [json.loads(line) for line in
                 (runs / "e2e-pr" / "trace.jsonl").read_text(encoding="utf-8")
                 .splitlines()]
        evs = [e["event"] for e in trace]
        assert "run_paused" in evs and "run_resumed" in evs
        assert evs[-1] == "run_end"
    finally:
        if task is not None and not task.done():
            task.cancel()
        srv.stop()
