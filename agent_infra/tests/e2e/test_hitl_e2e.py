"""E2E：request_human 跨真实 A2A 等待 + /internal/hitl 唤醒 + 心跳不超时。

agent（server 线程内）无超时等 Future，答案经真实 HTTP side 路由唤醒；
node_timeout_s=3 的窄预算下等待不被误杀（心跳持续延期语义已在 Task 5 单测覆盖，
20s 心跳间隔 > 测试时长，此处不重复触发）。
"""
from __future__ import annotations

import asyncio
import json

import a2a.client  # noqa: F401 —— 预热 engine 侧惰性 import，冷导入不吃 3s 节点预算
import httpx

from harness.engine import DEFAULT_PLAN, HarnessEngine
from harness.hitl import REGISTRY
from harness.tools.hitl import request_human
from tests.e2e.test_memory_ab import CANNED, _FakeServer, _free_port


async def _wait_pending(trace_id: str, timeout_s: float = 5.0) -> None:
    """轮询等 agent 真正挂起（替代固定 sleep：到点即作答，少耗窄预算窗口）。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    while loop.time() < deadline:
        if REGISTRY.pending_for(trace_id):
            return
        await asyncio.sleep(0.02)
    raise AssertionError(f"hitl not pending within {timeout_s}s")


async def test_hitl_wait_and_wake_over_real_a2a(tmp_path):
    runs = tmp_path / "runs"
    asked: dict = {}

    async def fake_run(run, prompt):
        tool = request_human(run, None)
        asked["q"] = "折扣率上限是多少？"
        asked["answer"] = await tool(asked["q"])   # 真实等待（无超时）
        return CANNED

    srv = _FakeServer(runs, fake_run, _free_port())
    srv.start()
    task: asyncio.Task | None = None
    try:
        engine = HarnessEngine(
            None, runs,
            agent_urls={"cr_agent": f"http://127.0.0.1:{srv.port}"})
        # 构造器无此 kwarg（一期即实例属性）：按现有属性名对齐。故意短——
        # 等人期间若预算不续期，node 会在 3s 处被杀，node_end 就不是 ok
        engine.node_timeout_s = 3
        task = asyncio.create_task(engine.execute_for(
            "e2e-hitl", {"repo": "x", "commit": "d"}, DEFAULT_PLAN))
        await _wait_pending("e2e-hitl")            # agent 已进入等待
        async with httpx.AsyncClient(trust_env=False, timeout=10.0) as cli:
            r = await cli.post(f"http://127.0.0.1:{srv.port}"
                               f"/internal/hitl/e2e-hitl",
                               json={"text": "上限 0.20"})
            assert r.status_code == 200
        await asyncio.wait_for(task, timeout=10)
        assert asked["answer"] == "上限 0.20"
        trace = [json.loads(line) for line in
                 (runs / "e2e-hitl" / "trace.jsonl").read_text(encoding="utf-8")
                 .splitlines()]
        assert any(e["event"] == "node_end" and
                   e["payload"]["status"] == "ok" for e in trace)  # 未被误杀
    finally:
        REGISTRY.cancel("e2e-hitl")  # 失败路径：唤醒等待，让 task 可收敛
        if task is not None and not task.done():
            task.cancel()
        srv.stop()
