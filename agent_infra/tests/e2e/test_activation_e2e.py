"""E2E：做实链路（八期 V1 新链）。#8 注入链（requirement→strategy→cr，fake
断言 upstream 键值）；#9 planning 真实 A2A（canned plan）选 8 节点全链
（requirement→strategy→cr→test_recall→case→script→execute→report），
case_executor 真实执行，report 产出 execution_report.md。fake agent 不烧真实 LLM。"""
from __future__ import annotations

import json
import socket
import threading
import time
from dataclasses import replace
from pathlib import Path

import uvicorn

from agent_server import build_a2a_app, load_agent_by_name
from harness.contract import ExecutionPlan
from harness.engine import HarnessEngine
from harness.sandbox.manager import SandboxManager
from harness.sandbox.worktree import WorktreeProvider

CR_CANNED = json.dumps({
    "issues": [{"file": "shop/stats.py", "line": 8, "severity": "high",
                "type": "exception", "desc": "bare except"}],
    "verdict": "request_changes", "summary": "s"})
REQ_OUT = {"task_type": "feature", "scope": ["shop/pricing.py"],
           "risks": [{"area": "折扣", "reason": "促销叠加优惠券"}],
           "acceptance": ["折扣率不超过 0.20 上限"]}
STR_OUT = {"focus_files": ["shop/pricing.py"],
           "check_order": [{"step": 1, "what": "折扣上限核对", "why": "资损面"}],
           "severity_hint": {"shop/pricing.py": "high"}}
REPORT_OUT = {"summary": "整体可控",
              "verdicts": [{"node": "cr_agent", "verdict": "request_changes"}],
              "stats": {"issues": 1},
              "markdown": "# 审查报告\n上游结论：requirement_agent 的验收 + "
                          "strategy_agent 的重点面 + case_executor 的执行结果。"}
SCRIPT = "# TC-001 generate\ndef test_ok():\n    assert True\n"
RECALL_OUT = {"recalled": [], "gaps": [], "recall_stats": {"queries": 1},
              "summary": "无召回"}
CASE_OUT = {"case_list": [
    {"id": "TC-001", "scenario": "必过用例", "action": "generate",
     "src": "", "linked_risk": "r1"}], "summary": "1 条"}
PLAN = {"plan_id": "P8",
        "nodes": [{"id": "requirement", "agent": "requirement_agent"},
                  {"id": "strategy", "agent": "strategy_agent"},
                  {"id": "cr", "agent": "cr_agent"},
                  {"id": "test_recall", "agent": "test_recall_agent"},
                  {"id": "case", "agent": "case_agent"},
                  {"id": "script", "agent": "script_agent"},
                  {"id": "execute", "program": "case_executor"},
                  {"id": "report", "agent": "report_agent"}],
        "edges": [["requirement", "strategy"], ["strategy", "cr"],
                  ["cr", "test_recall"], ["test_recall", "case"],
                  ["case", "script"], ["script", "execute"],
                  ["execute", "report"]]}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _FakeServer:
    """一端口一 agent（与 tests/e2e/test_e2e.py 同款）。"""

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


def _start_chain(runs, fns: dict) -> tuple[list, dict]:
    servers, urls = [], {}
    for agent, run_fn in fns.items():
        port = _free_port()
        urls[agent] = f"http://127.0.0.1:{port}"
        s = _FakeServer(runs, agent, run_fn, port)
        s.start()
        servers.append(s)
    return servers, urls


def _input_json(prompt: str) -> dict:
    """从 server 渲染的 prompt（引导语 + AgentInput JSON）里剥出输入对象。"""
    return json.loads(prompt[prompt.index("{"):])


async def test_upstream_chain_injection(tmp_path):  # 矩阵 #8
    runs = tmp_path / "runs"
    seen: dict = {}

    async def req_run(run, prompt):
        return json.dumps(REQ_OUT)

    async def str_run(run, prompt):
        seen["strategy_prompt"] = prompt
        return json.dumps(STR_OUT)

    async def cr_run(run, prompt):
        seen["cr_prompt"] = prompt
        return CR_CANNED

    servers, urls = _start_chain(runs, {
        "requirement_agent": req_run, "strategy_agent": str_run,
        "cr_agent": cr_run})
    plan = ExecutionPlan(
        plan_id="p6",
        nodes=[{"id": "requirement", "agent": "requirement_agent"},
               {"id": "strategy", "agent": "strategy_agent"},
               {"id": "cr", "agent": "cr_agent"}],
        edges=[["requirement", "strategy"], ["strategy", "cr"]])
    try:
        engine = HarnessEngine(None, runs, agent_urls=urls)
        await engine.execute_for("e2e-act-1",
                                 {"repo": "x", "commit": "defect-1"}, plan)
    finally:
        for s in servers:
            s.stop()

    strat = _input_json(seen["strategy_prompt"])
    assert strat["upstream"]["requirement_agent"] == REQ_OUT   # 一跳注入
    cr = _input_json(seen["cr_prompt"])
    assert cr["upstream"]["requirement_agent"] == REQ_OUT      # 全量前置注入
    assert cr["upstream"]["strategy_agent"] == STR_OUT
    # 真实产物链：requirement_brief / review_strategy 落 artifacts
    arts = runs / "e2e-act-1" / "artifacts"
    assert json.loads((arts / "requirement_brief.json").read_text()) == REQ_OUT
    assert json.loads((arts / "review_strategy.json").read_text()) == STR_OUT


async def test_planning_picks_full_chain_to_report(tmp_path):  # 矩阵 #9
    runs = tmp_path / "runs"
    seen: dict = {}

    async def plan_run(run, prompt):
        return json.dumps(PLAN)

    async def req_run(run, prompt):
        return json.dumps(REQ_OUT)

    async def str_run(run, prompt):
        return json.dumps(STR_OUT)

    async def cr_run(run, prompt):
        return CR_CANNED

    async def test_recall_run(run, prompt):
        return json.dumps(RECALL_OUT)

    async def case_run(run, prompt):
        return json.dumps(CASE_OUT)

    async def script_run(run, prompt):
        # case_executor（真实 Program 节点）要真实执行：往 per-run worktree
        # 落一个必过脚本（artifacts_dir 的兄弟目录即 runs/<rid>/sandbox）
        sandbox = Path(run.artifacts_dir).parent / "sandbox"
        sandbox.mkdir(parents=True, exist_ok=True)
        (sandbox / "test_cases.py").write_text(SCRIPT, encoding="utf-8")
        return SCRIPT

    async def report_run(run, prompt):
        seen["report_prompt"] = prompt
        return json.dumps(REPORT_OUT)

    servers, urls = _start_chain(runs, {
        "planning_agent": plan_run, "requirement_agent": req_run,
        "strategy_agent": str_run, "cr_agent": cr_run,
        "test_recall_agent": test_recall_run, "case_agent": case_run,
        "script_agent": script_run, "report_agent": report_run})
    try:
        engine = HarnessEngine(None, runs, agent_urls=urls)
        await engine.execute_for("e2e-act-2", {"repo": "x", "commit": "defect-1"})
    finally:
        for s in servers:
            s.stop()

    trace = [json.loads(ln) for ln in
             (runs / "e2e-act-2" / "trace.jsonl").read_text().splitlines()]
    node_order = [e["node_id"] for e in trace if e["event"] == "node_start"]
    assert node_order == ["requirement", "strategy", "cr", "test_recall",
                          "case", "script", "execute",
                          "report"]              # planning 选了新链
    rep_input = _input_json(seen["report_prompt"])
    assert rep_input["upstream"]["requirement_agent"] == REQ_OUT
    assert rep_input["upstream"]["case_executor"]["exit_code"] == 0  # 真实执行
    md = runs / "e2e-act-2" / "artifacts" / "execution_report.md"
    assert md.read_text(encoding="utf-8") == REPORT_OUT["markdown"]
