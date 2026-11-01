"""E2E：多 agent 闭环端到端（真实 A2A + fake agent + 真实 case_executor）。

跑一遍完整链路 commit → Planning → CR → test_recall → case → script →
case_executor → report → COMPLETED，比对真实产物内容（plan.json /
cr_report.json / test_cases.json 的实际内容）与 fixture
（tests/e2e/fixtures/expected_flow.json），不止比状态。fake agent 返回
确定性 canned 输出，不烧真实 LLM；case_executor 是真实 Program 节点（跑 pytest）。
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
from harness.engine import HarnessEngine
from harness.sandbox.manager import SandboxManager
from harness.sandbox.worktree import WorktreeProvider

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "expected_flow.json")
    .read_text(encoding="utf-8"))


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _FakeServer:
    def __init__(self, runs_root, agent, run_fn, port):
        mgr = SandboxManager(WorktreeProvider(allowed_cmds=frozenset()),
                             runs_root)
        spec = replace(load_agent_by_name(agent),
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


async def test_e2e_multi_agent_flow(tmp_path):
    runs = tmp_path / "runs"
    trace_id = "e2e-1"

    # 预置 worktree + 测试脚本：case_executor（真实 Program 节点）要真实执行
    worktree = runs / trace_id / "sandbox"
    worktree.mkdir(parents=True)
    (worktree / "test_cases.py").write_text(
        FIXTURE["test_cases"]["script"], encoding="utf-8")

    async def plan_run(run, prompt):
        return json.dumps(FIXTURE["plan"])

    async def cr_run(run, prompt):
        return json.dumps(FIXTURE["cr_report"])

    async def test_recall_run(run, prompt):
        return json.dumps({"recalled": [], "gaps": [], "recall_stats": {},
                           "summary": "无召回"})

    async def case_run(run, prompt):
        # 一条 generate 条目：id 与脚本注释锚点一致（cover_ratio=1.0 不告警）
        return json.dumps({"case_list": [
            {"id": "TC-001", "scenario": "必过用例", "action": "generate",
             "src": "", "linked_risk": "r1"}], "summary": "1 条"})

    async def script_run(run, prompt):
        return FIXTURE["test_cases"]["script"]

    async def report_run(run, prompt):
        return json.dumps({"summary": "s", "verdicts": [],
                           "markdown": "# 审查报告\n"})

    servers, ports = [], {}
    for agent, run_fn in [("planning_agent", plan_run),
                          ("cr_agent", cr_run),
                          ("test_recall_agent", test_recall_run),
                          ("case_agent", case_run),
                          ("script_agent", script_run),
                          ("report_agent", report_run)]:
        port = _free_port()
        ports[agent] = f"http://127.0.0.1:{port}"
        s = _FakeServer(runs, agent, run_fn, port)
        s.start()
        servers.append(s)

    try:
        engine = HarnessEngine(None, runs, agent_urls=ports)
        await engine.execute_for(trace_id, {"repo": "x", "commit": "defect-1"})
    finally:
        for s in servers:
            s.stop()

    # 真实结果 vs fixture（含产物内容）
    trace = [json.loads(line) for line in
             (runs / trace_id / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    node_order = [e["node_id"] for e in trace if e["event"] == "node_start"]
    triggers = [e["payload"]["trigger"] for e in trace
                if e["event"] == "state_transition"]
    run_end = next(e for e in trace if e["event"] == "run_end")

    assert node_order == FIXTURE["node_order"]
    assert triggers == FIXTURE["state_transition_triggers"]
    assert run_end["payload"]["status"] == FIXTURE["final_status"]

    # 产物内容逐字段比对（端到端数据流正确性，非只比状态）
    artifacts = runs / trace_id / "artifacts"
    assert json.loads((artifacts / "plan.json").read_text()) == FIXTURE["plan"]
    assert json.loads((artifacts / "cr_report.json").read_text()) == FIXTURE["cr_report"]
    assert json.loads((artifacts / "test_cases.json").read_text()) == FIXTURE["test_cases"]

    # case_executor 真实执行结果落进 checkpoint 的 node_outputs
    checkpoint = json.loads((runs / trace_id / "checkpoint.json").read_text())
    execute_output = checkpoint["node_outputs"]["execute"]["output_data"]
    assert execute_output["exit_code"] == 0
    assert "passed" in execute_output["stdout"]
