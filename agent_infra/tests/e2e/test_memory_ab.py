"""E2E：memory 开（Hybrid）/ 关（Noop）经真实 A2A 的 recall 注入 + record 落盘。

fake agent 返回确定性 canned 输出，不烧真实 LLM；验证 memory 的召回确实到达
agent 的 prompt（history 序列化进 AgentInput），且 record 在 finally 落盘。
"""
from __future__ import annotations

import json
import socket
import threading
import time
from dataclasses import replace
from pathlib import Path

import uvicorn

from agent_server import build_a2a_app, load_agent_by_name
from harness.engine import DEFAULT_PLAN, HarnessEngine
from harness.memory import HybridMemory
from harness.sandbox.manager import SandboxManager
from harness.sandbox.worktree import WorktreeProvider

CANNED = json.dumps({
    "issues": [{"file": "shop/stats.py", "line": 8, "severity": "high",
                "type": "exception", "desc": "bare except"}],
    "verdict": "request_changes", "summary": "s"})


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _conventions(tmp_path: Path) -> Path:
    p = tmp_path / "conventions.json"
    p.write_text(json.dumps([
        {"id": "c1", "kind": "team_convention",
         "text": "折扣率上限20%", "tags": ["discount"], "repo": None}],
        ensure_ascii=False), encoding="utf-8")
    return p


class _FakeServer:
    def __init__(self, runs_root, run_fn, port):
        self.port = port
        mgr = SandboxManager(WorktreeProvider(allowed_cmds=frozenset()), runs_root)
        spec = replace(load_agent_by_name("cr_agent"),
                       url=f"http://127.0.0.1:{port}")
        self.app = build_a2a_app(runs_root, mgr, spec, run_agent=run_fn)
        self.server = uvicorn.Server(uvicorn.Config(
            self.app, host="127.0.0.1", port=port, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self):
        self.thread.start()
        for _ in range(100):
            if self.server.started:
                break
            time.sleep(0.05)

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=5)


async def test_memory_recall_reaches_agent_and_records(tmp_path):
    runs = tmp_path / "runs"
    seen: dict = {}

    async def cr_run(run, prompt):
        seen["prompt"] = prompt
        return CANNED

    srv = _FakeServer(runs, cr_run, _free_port())
    srv.start()
    try:
        engine = HarnessEngine(
            None, runs,
            memory=HybridMemory(runs, _conventions(tmp_path)),
            agent_urls={"cr_agent": f"http://127.0.0.1:{srv.port}"})
        await engine.execute_for(
            "e2e-mem-1", {"repo": "x", "commit": "defect-1", "context_id": "repo:x"},
            DEFAULT_PLAN)
    finally:
        srv.stop()

    assert "折扣率上限20%" in seen["prompt"]          # recall 注入到 agent prompt
    exp = runs / "memory" / "experiences.jsonl"
    assert exp.exists()                                # record 在 finally 落盘
    assert "past_review" in exp.read_text()


async def test_noop_memory_does_not_inject(tmp_path):
    runs = tmp_path / "runs"
    seen: dict = {}

    async def cr_run(run, prompt):
        seen["prompt"] = prompt
        return CANNED

    srv = _FakeServer(runs, cr_run, _free_port())
    srv.start()
    try:
        engine = HarnessEngine(
            None, runs, agent_urls={"cr_agent": f"http://127.0.0.1:{srv.port}"})
        await engine.execute_for("e2e-mem-0", {"repo": "x", "commit": "defect-1"},
                                 DEFAULT_PLAN)
    finally:
        srv.stop()

    assert "折扣率上限20%" not in seen["prompt"]       # Noop：无 recall 注入
    assert not (runs / "memory" / "experiences.jsonl").exists()
