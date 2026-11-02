"""E2E：八期全链（#12 含召回双报告）与 diagnose 选入（#13）。fake agent 不烧 LLM。"""
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

CR_CANNED = json.dumps({
    "issues": [{"file": "shop/pricing.py", "line": 3, "severity": "mid",
                "type": "consistency", "desc": "新增 50 元档折扣改变 tier_discount 行为"}],
    "verdict": "request_changes", "summary": "s"})
RECALL_OUT = {"recalled": [{"case_id": "TC-002", "source": "test-cases.md",
                            "score": 0.8,
                            "matched_risk": "新增 50 元档折扣改变 tier_discount 行为"}],
              "gaps": [], "recall_stats": {"queries": 1, "skipped": 0, "hits": 1},
              "summary": "召回 1"}
CHANGE_OUT = {"summary": "该测什么", "risk_n": 1, "recalled_n": 1,
              "recommended_n": 1,
              "markdown": "# 变更分析报告\n风险 1 条；召回 TC-002 可复用；建议 reuse 1 条"}
CASE_OUT = {"case_list": [
    {"id": "TC-002", "scenario": "阶梯折扣档位边界", "action": "reuse",
     "src": "tests/test_pricing.py::test_tier_discount",
     "linked_risk": "新增 50 元档折扣改变 tier_discount 行为"}],
    "summary": "reuse 1"}
PASS_SCRIPT = ("# TC-002 reuse: tests/test_pricing.py::test_tier_discount\n"
               "def test_tc_002():\n    assert True\n")
FAIL_SCRIPT = "# TC-002\ndef test_tc_002():\n    assert False, '档位变更未同步'\n"
REPORT_OUT = {"summary": "测得怎样",
              "verdicts": [{"node": "cr_agent", "verdict": "request_changes"}],
              "stats": {"issues": 1, "tests_passed": 1, "tests_total": 1,
                        "pass_rate": 1.0},
              "root_causes_n": 0, "markdown": "# 执行报告\n通过率 100%"}
DIAG_OUT = {"root_causes": [{"case": "test_tc_002", "cause": "档位变更未同步断言",
                             "evidence": "shop/pricing.py:3"}], "summary": "定位 1 条"}
FULL_PLAN = {   # #12：显式 9 节点链（req→strategy→cr→recall→change_report→…→report）
    "plan_id": "P8",
    "nodes": [{"id": "requirement", "agent": "requirement_agent"},
              {"id": "strategy", "agent": "strategy_agent"},
              {"id": "cr", "agent": "cr_agent"},
              {"id": "recall", "agent": "test_recall_agent"},
              {"id": "change_report", "agent": "change_report_agent"},
              {"id": "case", "agent": "case_agent"},
              {"id": "script", "agent": "script_agent"},
              {"id": "execute", "program": "case_executor"},
              {"id": "report", "agent": "report_agent"}],
    "edges": [["requirement", "strategy"], ["strategy", "cr"], ["cr", "recall"],
              ["recall", "change_report"], ["change_report", "case"],
              ["case", "script"], ["script", "execute"], ["execute", "report"]]}
DIAG_PLAN = {   # #13：canned planning 选 diagnose（execute 与 report 之间）
    "plan_id": "P8d",
    "nodes": [{"id": "cr", "agent": "cr_agent"},
              {"id": "recall", "agent": "test_recall_agent"},
              {"id": "case", "agent": "case_agent"},
              {"id": "script", "agent": "script_agent"},
              {"id": "execute", "program": "case_executor"},
              {"id": "diagnose", "agent": "diagnose_agent"},
              {"id": "report", "agent": "report_agent"}],
    "edges": [["cr", "recall"], ["recall", "case"], ["case", "script"],
              ["script", "execute"], ["execute", "diagnose"], ["diagnose", "report"]]}
REQ_OUT = {"task_type": "feature", "scope": ["shop/pricing.py"], "risks": [],
           "acceptance": []}
STR_OUT = {"focus_files": ["shop/pricing.py"], "check_order": [], "severity_hint": {}}


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


async def test_full_chain_dual_reports(tmp_path, monkeypatch):  # 矩阵 #12
    # 九期审阅门控：plan 含 report → 测试用 REVIEW_AUTO 直通（accept 语义照走）
    monkeypatch.setenv("AGENT_INFRA_REVIEW_AUTO", "1")
    runs = tmp_path / "runs"
    seen: dict = {}

    async def _req(run, prompt):
        return json.dumps(REQ_OUT)

    async def _str(run, prompt):
        return json.dumps(STR_OUT)

    async def _cr(run, prompt):
        return CR_CANNED

    async def _recall(run, prompt):
        seen["recall_prompt"] = prompt
        return json.dumps(RECALL_OUT)

    async def _change(run, prompt):
        seen["change_prompt"] = prompt
        return json.dumps(CHANGE_OUT)

    async def _case(run, prompt):
        seen["case_prompt"] = prompt
        return json.dumps(CASE_OUT)

    async def _script(run, prompt):
        sandbox = Path(run.artifacts_dir).parent / "sandbox"
        sandbox.mkdir(parents=True, exist_ok=True)
        (sandbox / "test_cases.py").write_text(PASS_SCRIPT, encoding="utf-8")
        return PASS_SCRIPT

    async def _report(run, prompt):
        seen["report_prompt"] = prompt
        out = dict(REPORT_OUT)
        return json.dumps(out)

    servers, urls = _start_chain(runs, {
        "requirement_agent": _req, "strategy_agent": _str, "cr_agent": _cr,
        "test_recall_agent": _recall, "change_report_agent": _change,
        "case_agent": _case, "script_agent": _script, "report_agent": _report})
    from harness.contract import ExecutionPlan
    plan = ExecutionPlan(plan_id=FULL_PLAN["plan_id"], nodes=FULL_PLAN["nodes"],
                         edges=FULL_PLAN["edges"])
    try:
        engine = HarnessEngine(None, runs, agent_urls=urls)
        await engine.execute_for("e2e-sdlc-1", {"repo": "x", "commit": "defect-1"},
                                 plan)
    finally:
        for s in servers:
            s.stop()

    arts = runs / "e2e-sdlc-1" / "artifacts"
    # reuse 条目源于语料：case_list 引用召回的 TC-002
    case_list = json.loads((arts / "case_list.json").read_text(encoding="utf-8"))
    reuse = [c for c in case_list["case_list"] if c["action"] == "reuse"]
    assert reuse and reuse[0]["id"] == RECALL_OUT["recalled"][0]["case_id"]
    assert reuse[0]["src"].startswith("tests/test_pricing.py")
    # 召回注入：recall prompt 的 upstream 含 cr 结论
    assert "cr_agent" in _input_json(seen["recall_prompt"])["upstream"]
    # change_report 在 executor 前落盘（trace 事件序 + 产物存在）
    trace = [json.loads(ln) for ln in
             (runs / "e2e-sdlc-1" / "trace.jsonl").read_text().splitlines()]
    events = [(e["event"], e["node_id"]) for e in trace]
    assert events.index(("node_end", "change_report")) < events.index(
        ("node_start", "execute"))
    assert (arts / "change_report.md").read_text(encoding="utf-8") == CHANGE_OUT["markdown"]
    # 执行报告含 pass_rate
    assert (arts / "execution_report.md").exists()
    rep_up = _input_json(seen["report_prompt"])["upstream"]
    assert rep_up["case_executor"]["exit_code"] == 0        # 真实执行


async def test_diagnose_selected_on_failure(tmp_path, monkeypatch):  # 矩阵 #13
    # 九期审阅门控：同上，REVIEW_AUTO 直通
    monkeypatch.setenv("AGENT_INFRA_REVIEW_AUTO", "1")
    runs = tmp_path / "runs"
    seen: dict = {}

    async def _plan(run, prompt):
        return json.dumps(DIAG_PLAN)

    async def _cr(run, prompt):
        return CR_CANNED

    async def _recall(run, prompt):
        return json.dumps(RECALL_OUT)

    async def _case(run, prompt):
        return json.dumps(CASE_OUT)

    async def _script(run, prompt):     # 必败脚本 → executor exit_code=1
        sandbox = Path(run.artifacts_dir).parent / "sandbox"
        sandbox.mkdir(parents=True, exist_ok=True)
        (sandbox / "test_cases.py").write_text(FAIL_SCRIPT, encoding="utf-8")
        return FAIL_SCRIPT

    async def _diagnose(run, prompt):
        seen["diagnose_prompt"] = prompt
        return json.dumps(DIAG_OUT)

    async def _report(run, prompt):
        seen["report_prompt"] = prompt
        return json.dumps(REPORT_OUT)

    servers, urls = _start_chain(runs, {
        "planning_agent": _plan, "cr_agent": _cr, "test_recall_agent": _recall,
        "case_agent": _case, "script_agent": _script,
        "diagnose_agent": _diagnose, "report_agent": _report})
    try:
        engine = HarnessEngine(None, runs, agent_urls=urls)
        await engine.execute_for("e2e-sdlc-2", {"repo": "x", "commit": "defect-1"})
    finally:
        for s in servers:
            s.stop()

    trace = [json.loads(ln) for ln in
             (runs / "e2e-sdlc-2" / "trace.jsonl").read_text().splitlines()]
    node_order = [e["node_id"] for e in trace if e["event"] == "node_start"]
    assert node_order == ["cr", "recall", "case", "script", "execute",
                          "diagnose", "report"]              # planning 选了 diagnose
    diag_up = _input_json(seen["diagnose_prompt"])["upstream"]
    exec_up = diag_up["case_executor"]
    # 失败 stdout 超 500 字上游预算被 _clip_upstream 截断（exit_code 是首键，
    # head 保序可见）——两形态都证明 executor 失败结果送达 diagnose 被消费
    assert exec_up.get("exit_code") == 1 or (
        exec_up.get("_truncated") is True and '"exit_code": 1,' in exec_up["head"])
    rep_up = _input_json(seen["report_prompt"])["upstream"]
    assert rep_up["diagnose_agent"]["root_causes"] == DIAG_OUT["root_causes"]  # 进执行报告
    assert (runs / "e2e-sdlc-2" / "artifacts" / "diagnose.json").exists()
