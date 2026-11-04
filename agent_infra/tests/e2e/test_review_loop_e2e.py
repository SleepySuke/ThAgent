"""E2E：九期审阅回路三用例（#19 accept / #20 replan / #21 飞轮 roundtrip）。

样板取 tests/e2e/test_sdlc_chain_e2e.py（_FakeServer/_start_chain，fake 全链
零 LLM）。不设 REVIEW_AUTO——真实走 park → 后台裁决（审阅回路语义本体）。
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from harness.engine import HarnessEngine
from tests.e2e.test_sdlc_chain_e2e import (
    CASE_OUT,
    CHANGE_OUT,
    CR_CANNED,
    RECALL_OUT,
    REPORT_OUT,
    REQ_OUT,
    STR_OUT,
    _input_json,
    _start_chain,
)

REVIEW_PLAN = {  # 显式 plan 含 report（审阅门控默认激活的前提）；边集合法（DAG）
    "plan_id": "P9",
    "nodes": [{"id": "requirement", "agent": "requirement_agent"},
              {"id": "strategy", "agent": "strategy_agent"},
              {"id": "cr", "agent": "cr_agent"},
              {"id": "recall", "agent": "test_recall_agent"},
              {"id": "case", "agent": "case_agent"},
              {"id": "script", "agent": "script_agent"},
              {"id": "execute", "program": "case_executor"},
              {"id": "report", "agent": "report_agent"}],
    "edges": [["requirement", "strategy"], ["strategy", "cr"],
              ["cr", "recall"], ["recall", "case"], ["case", "script"],
              ["script", "execute"], ["execute", "report"]]}
PASS_SCRIPT = "def test_tc_002():\n    assert True\n"


async def _wait_review(engine, trace_id, timeout=3.0):
    """等 review_event 已建未 set（新一轮待裁决；排除已 set 未消费的旧事件）。"""
    async def ready():
        h = engine._runs.get(trace_id)
        return (h is not None and h.review_event is not None
                and not h.review_event.is_set())
    deadline = asyncio.get_running_loop().time() + timeout
    while not await ready():
        if asyncio.get_running_loop().time() > deadline:
            raise TimeoutError("not in review pending")
        await asyncio.sleep(0.01)


def _events(runs, trace_id):
    return [json.loads(line) for line in
            (runs / trace_id / "trace.jsonl").read_text().splitlines()]


def _plan():
    """REVIEW_PLAN → ExecutionPlan（显式含 report，审阅门控激活）。"""
    from harness.contract import ExecutionPlan
    return ExecutionPlan(plan_id=REVIEW_PLAN["plan_id"],
                         nodes=REVIEW_PLAN["nodes"], edges=REVIEW_PLAN["edges"])


def _fm(path: Path) -> dict[str, str]:
    """蒸馏条目 frontmatter 手解析（与 distill 零依赖约定一致）。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].strip() == "---"
    out = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip()
    return out


def _chain_fns(seen: dict, *, report_out=None, case_src=None) -> dict:
    """REVIEW_PLAN 各 agent 的 fake run_fn（script 真写沙箱、其余 canned）。"""

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
        return json.dumps(CHANGE_OUT)

    async def _case(run, prompt):
        seen["case_prompt"] = prompt
        out = json.loads(json.dumps(CASE_OUT))    # 深拷贝防跨 run 污染
        if case_src is not None:
            out["case_list"][0]["src"] = case_src(seen)
        return json.dumps(out)

    async def _script(run, prompt):
        sandbox = Path(run.artifacts_dir).parent / "sandbox"
        sandbox.mkdir(parents=True, exist_ok=True)
        (sandbox / "test_cases.py").write_text(PASS_SCRIPT, encoding="utf-8")
        return PASS_SCRIPT

    async def _report(run, prompt):
        seen["report_prompt"] = prompt
        return json.dumps(report_out or REPORT_OUT)

    return {"requirement_agent": _req, "strategy_agent": _str,
            "cr_agent": _cr, "test_recall_agent": _recall,
            "change_report_agent": _change, "case_agent": _case,
            "script_agent": _script, "report_agent": _report}


async def test_review_accept_completes_and_distills(tmp_path, monkeypatch):
    """#19 审阅回路：跑完 park → 后台 accept → COMPLETED + 蒸馏 + 快照。"""
    monkeypatch.delenv("AGENT_INFRA_REVIEW_AUTO", raising=False)
    runs = tmp_path / "runs"
    corpus = tmp_path / "distilled"
    seen: dict = {}
    servers, urls = _start_chain(runs, _chain_fns(seen))
    try:
        engine = HarnessEngine(None, runs, agent_urls=urls)
        engine.distill_corpus_dir = corpus
        task = asyncio.create_task(engine.execute_for(
            "e2e-rev-1", {"repo": "x", "commit": "defect-2"}, _plan()))
        await _wait_review(engine, "e2e-rev-1")
        # park 证据：事件 + checkpoint 双落
        events = _events(runs, "e2e-rev-1")
        assert any(e["event"] == "review_pending" for e in events)
        cp = json.loads((runs / "e2e-rev-1" / "checkpoint.json").read_text())
        assert cp["harness_state"] == "review_pending"
        engine.review_run("e2e-rev-1", "accept")
        await task
    finally:
        for s in servers:
            s.stop()
    cp = json.loads((runs / "e2e-rev-1" / "checkpoint.json").read_text())
    assert cp["harness_state"] == "completed"
    # 蒸馏落盘 + frontmatter provenance（钉桩消费闭环）
    entries = list(corpus.glob("*.md"))
    assert entries
    ex = next(p for p in entries if p.name.startswith("exemplar-"))
    fm = _fm(ex)
    assert fm["source_run_id"] == "e2e-rev-1"
    assert fm["model"] and len(fm["prompt_sha"]) == 12
    # accepted 快照存在（replan 版本锚）
    assert (runs / "e2e-rev-1" / "review" / "accepted_r1.json").exists()


async def test_review_reject_replans_round2(tmp_path, monkeypatch):
    """#20 replan：reject+feedback → round=2 重规划（feedback 进 planning）→
    二轮链真实执行 + 再 park → accept 收尾。"""
    monkeypatch.delenv("AGENT_INFRA_REVIEW_AUTO", raising=False)
    runs = tmp_path / "runs"
    seen: dict = {}
    feedback = "补充边界测试"

    async def _plan(run, prompt):
        seen["plan_prompt"] = prompt
        return json.dumps(REVIEW_PLAN)

    fns = _chain_fns(seen)
    fns["planning_agent"] = _plan
    servers, urls = _start_chain(runs, fns)
    try:
        engine = HarnessEngine(None, runs, agent_urls=urls)
        engine.distill_corpus_dir = tmp_path / "distilled"
        task = asyncio.create_task(
            engine.execute_for("e2e-rev-2", {"repo": "x", "commit": "defect-2"}))
        await _wait_review(engine, "e2e-rev-2")
        engine.review_run("e2e-rev-2", "reject", feedback)
        await _wait_review(engine, "e2e-rev-2")   # 二轮再审（真实跑完新链后 park）
        engine.review_run("e2e-rev-2", "accept")
        await task
    finally:
        for s in servers:
            s.stop()
    # replan feedback 注入 planning（_input_json 剥引导语；feedback 在 input_data 槽）
    assert _input_json(seen["plan_prompt"])["input_data"][
        "hitl_feedback"] == {"text": feedback}
    events = _events(runs, "e2e-rev-2")
    assert len([e for e in events if e["event"] == "review_pending"]) == 2
    assert any(e["event"] == "review_rejected" for e in events)
    # 二轮链真实执行（二轮 node_start 计数）+ 报告落盘 + round=2 checkpoint
    starts = [e["node_id"] for e in events if e["event"] == "node_start"]
    assert starts.count("cr") == 2 and starts.count("report") == 2
    assert (runs / "e2e-rev-2" / "artifacts" / "execution_report.md").exists()
    cp = json.loads((runs / "e2e-rev-2" / "checkpoint.json").read_text())
    assert cp["round"] == 2 and cp["harness_state"] == "completed"
    assert (runs / "e2e-rev-2" / "review" / "accepted_r2.json").exists()


def _assert_exemplar(corpus, name, tid, keyword):
    """蒸馏条目 frontmatter provenance + 正文含可检索关键词。"""
    ex = corpus / name
    assert ex.exists()
    fm = _fm(ex)
    assert (fm["source_run_id"], fm["round"]) == (tid, "1")
    assert fm["model"] and len(fm["prompt_sha"]) == 12
    assert keyword in ex.read_text(encoding="utf-8")
    return ex


def _make_kb(runs, knowledge):
    """真 KnowledgeBase（Tfidf，零 API）——corpus 指向测试隔离目录。"""
    from harness.knowledge import KnowledgeBase
    from harness.memory import TfidfEmbedder
    return KnowledgeBase(runs / "kb", corpus_dir=knowledge,
                         embedder=TfidfEmbedder())


def _assert_reuse_and_bypass(runs, corpus, ex_name, seen, mtime_before):
    """case reuse src 指向命中条目 + use_count 旁路 +1 且 md mtime 不变。"""
    case_list = json.loads((runs / "e2e-fly-2" / "artifacts" / "case_list.json")
                           .read_text(encoding="utf-8"))
    reuse = [c for c in case_list["case_list"] if c["action"] == "reuse"]
    assert reuse and reuse[0]["src"] == seen["hit_path"]
    assert seen["hit_path"].startswith("distilled/exemplar-e2e-fly-1")
    counts = json.loads((corpus / ".counts.json").read_text(encoding="utf-8"))
    assert counts[f"distilled/{ex_name}"]["use"] == 1   # #21b
    ex = corpus / ex_name
    assert ex.stat().st_mtime == mtime_before   # 旁路计数不碰 md
    from harness.policy import NODE_POLICIES  # #21c 最小断言（e2e 钉 policy 面）
    assert "search_knowledge" in NODE_POLICIES["report_agent"].allowed_tools


async def test_flywheel_roundtrip(tmp_path, monkeypatch):
    """#21 飞轮：run1 accept 蒸馏 → 真实 KB 命中蒸馏条目 → run2 经
    search_knowledge 检索复用（use_count 旁路 +1、md 不变）→ case reuse src
    指向蒸馏条目（#21b/#21c）。"""
    monkeypatch.delenv("AGENT_INFRA_REVIEW_AUTO", raising=False)
    runs = tmp_path / "runs"
    knowledge = tmp_path / "knowledge"
    corpus = knowledge / "distilled"
    seen: dict = {}
    keyword = "阶梯折扣档位边界契约冲突"    # 蒸馏正文可检索关键词
    report_out = {**REPORT_OUT,
                  "markdown": f"# 执行报告\n{keyword}，需同步用例库。"}

    def _case_src(s):
        return s.get("hit_path", "")

    def _engine(agent_urls):
        eng = HarnessEngine(None, runs, agent_urls=agent_urls)
        eng.distill_corpus_dir = corpus
        return eng

    async def _run(srvs, urls_, tid):
        servers, urls = srvs, urls_
        try:
            engine = _engine(urls)
            task = asyncio.create_task(engine.execute_for(
                tid, {"repo": "x", "commit": "defect-2"}, _plan()))
            await _wait_review(engine, tid)
            engine.review_run(tid, "accept")
            await task
        finally:
            for s in servers:
                s.stop()

    ex_name = "exemplar-e2e-fly-1-r1-1.md"
    servers, urls = _start_chain(runs, _chain_fns(seen, report_out=report_out,
                                                  case_src=_case_src))
    await _run(servers, urls, "e2e-fly-1")

    # 蒸馏落盘 + 真 KB（Tfidf，零 API）惰性重建索引后命中蒸馏条目
    ex = _assert_exemplar(corpus, ex_name, "e2e-fly-1", keyword)
    kb2 = _make_kb(runs, knowledge)
    assert any(h["path"] == f"distilled/{ex_name}"
               for h in kb2.search(keyword))

    # run2：fake test_recall 内调真实 search_knowledge 工具（bump use 走旁路）
    from harness.contract import RunContext
    from harness.tools import knowledge as tk
    monkeypatch.setattr(tk, "_KB", kb2)

    async def _recall(run, prompt):
        tool = tk.search_knowledge(
            RunContext(trace_id=run.trace_id, repo_path="x", commit="d"), None)
        await tool(keyword)
        for h in kb2.search(keyword):
            if h["path"].startswith("distilled/exemplar-e2e-fly-1"):
                seen["hit_path"] = h["path"]
        return json.dumps(RECALL_OUT)

    fns2 = _chain_fns(seen, case_src=_case_src)
    fns2["test_recall_agent"] = _recall
    servers2, urls2 = _start_chain(runs, fns2)
    mtime_before = ex.stat().st_mtime
    await _run(servers2, urls2, "e2e-fly-2")

    _assert_reuse_and_bypass(runs, corpus, ex_name, seen, mtime_before)
