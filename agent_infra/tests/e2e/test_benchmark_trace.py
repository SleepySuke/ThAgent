"""E2E：node_start payload 钉桩（真实 A2A + DEFAULT_PLAN，fake agent 不烧 LLM）。"""
import json
import socket
import threading
import time
from dataclasses import replace

import uvicorn

from agent_server import build_a2a_app, load_agent_by_name
from harness.engine import DEFAULT_PLAN, HarnessEngine
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


async def test_node_start_payload_via_real_a2a(tmp_path):
    runs = tmp_path / "runs"

    async def cr_run(run, prompt):
        return CANNED

    srv = _FakeServer(runs, cr_run, _free_port())
    srv.start()
    try:
        engine = HarnessEngine(
            None, runs, agent_urls={"cr_agent": f"http://127.0.0.1:{srv.port}"})
        await engine.execute_for("e2e-ns", {"repo": "x", "commit": "defect-1"},
                                 DEFAULT_PLAN)
    finally:
        srv.stop()

    starts = [json.loads(ln) for ln in
              (runs / "e2e-ns" / "trace.jsonl").read_text().splitlines()
              if json.loads(ln)["event"] == "node_start"]
    assert starts[0]["payload"]["agent"] == "cr_agent"
    assert starts[0]["payload"]["upstream"] == {}          # 首节点无上游
