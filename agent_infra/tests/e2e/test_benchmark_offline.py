"""E2E：离线 scorer 对真实/引擎产出的 run 打分（矩阵 #11 + 引擎链路钉桩）。

#11 用六期 make smoke-agents 的真实 run（trace 含真实 tool_call 事件）——
产物不存在时 skip（冒烟烧 LLM，runs/ 不入库）；另一测用 fake A2A 跑真实
引擎链（不烧 LLM）验证 scorer 消费引擎真实产出的 trace/artifacts 形状。
"""
import json
import socket
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest
import uvicorn

import eval.benchmark as bm
from agent_server import build_a2a_app, load_agent_by_name
from harness.contract import ExecutionPlan
from harness.engine import HarnessEngine
from harness.sandbox.manager import SandboxManager
from harness.sandbox.worktree import WorktreeProvider

ROOT = Path(__file__).resolve().parents[2]
SMOKE = ROOT / "runs" / "smoke-agents"

CANNED = json.dumps({
    "issues": [{"file": "shop/stats.py", "line": 8, "severity": "high",
                "type": "exception", "desc": "bare except"}],
    "verdict": "request_changes", "summary": "s"})
SCRIPT = "# TC-001 generate\ndef test_ok():\n    assert True\n"
RECALL_OUT = json.dumps({"recalled": [], "gaps": [], "recall_stats": {},
                         "summary": "无召回"})
CASE_OUT = json.dumps({"case_list": [
    {"id": "TC-001", "scenario": "必过用例", "action": "generate",
     "src": "", "linked_risk": "r1"}], "summary": "1 条"})
PLAN = ExecutionPlan(
    plan_id="p", nodes=[{"id": "cr", "agent": "cr_agent"},
                        {"id": "test_recall", "agent": "test_recall_agent"},
                        {"id": "case", "agent": "case_agent"},
                        {"id": "script", "agent": "script_agent"},
                        {"id": "exec", "program": "case_executor"}],
    edges=[["cr", "test_recall"], ["test_recall", "case"],
           ["case", "script"], ["script", "exec"]])


def test_offline_scores_real_smoke_run():  # 矩阵 #11
    if not (SMOKE / "trace.jsonl").exists():
        pytest.skip("需先 make smoke-agents 产出真实 run")
    row = bm.score_run(bm.load_golden()["defect-1"], SMOKE)
    tc, tk = row["tool_calling"], row["task_completion"]
    assert tc["legality"] == 1.0              # 真实冒烟零越权（设计 §6 验收）
    assert 0.0 < tc["must_use_hit"] <= 1.0    # 必用工具基本触达
    assert tk["e2e_done"] is True
    assert 0.0 <= tk["cr_hit"] <= 1.0         # 指标在合理域


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _FakeServer:
    """一端口一 agent（与 tests/e2e/test_activation_e2e.py 同款）。"""

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


async def test_offline_scores_engine_run(tmp_path):
    runs = tmp_path / "runs"

    async def cr_run(run, prompt):
        return CANNED

    async def test_recall_run(run, prompt):
        return RECALL_OUT

    async def case_run(run, prompt):
        return CASE_OUT

    async def script_run(run, prompt):
        # case_executor（真实 Program 节点）要真实执行：预置必过脚本
        sandbox = Path(run.artifacts_dir).parent / "sandbox"
        sandbox.mkdir(parents=True, exist_ok=True)
        (sandbox / "test_cases.py").write_text(SCRIPT, encoding="utf-8")
        return SCRIPT

    servers, urls = [], {}
    for agent, fn in (("cr_agent", cr_run), ("test_recall_agent", test_recall_run),
                      ("case_agent", case_run), ("script_agent", script_run)):
        port = _free_port()
        urls[agent] = f"http://127.0.0.1:{port}"
        s = _FakeServer(runs, agent, fn, port)
        s.start()
        servers.append(s)
    try:
        engine = HarnessEngine(None, runs, agent_urls=urls)
        await engine.execute_for("e2e-bench", {"repo": "x", "commit": "defect-1"},
                                 PLAN)
    finally:
        for s in servers:
            s.stop()

    run_dirs, single = bm.collect_offline(runs / "e2e-bench")
    assert single and list(run_dirs) == ["defect-1"]      # 单 run 报告模式
    row = bm.score_run(bm.load_golden()["defect-1"], run_dirs["defect-1"])
    tk, tc = row["task_completion"], row["tool_calling"]
    assert tk["e2e_done"] is True
    assert tk["cr_hit"] == 1.0        # canned 命中 golden defect-1
    assert tk["plan_match"] is None   # 显式 plan 无 plan.json → N/A（矩阵 #4）
    assert tk["test_cover"] == 1.0    # executor 真执行（checkpoint 含 exit_code）
    assert tc["legality"] == 1.0      # fake agent 无 tool 事件（空集如实）
    assert tc["must_use_hit"] == 0.0  # 无 tool 事件 → 如实 0（矩阵 #3 语义）
