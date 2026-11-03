"""九期 Task 6：distill_executor 机械蒸馏（档 1，零 LLM）+ engine accept 接线。

矩阵 #7（产物缺失诚实降级）/#8（蒸馏失败不阻断 COMPLETED）/#21（frontmatter
provenance 断言）。engine 侧 in-proc fake 手法与 tests/unit/test_engine_review.py
一致（V2a-2 平移后的 auto/手动 accept 两条路径都要验蒸馏）。
"""
import asyncio
import json

import pytest

from harness.contract import AgentOutput, ExecutionPlan
from harness.engine import HarnessEngine
from harness.programs import distill_executor

CR_OUT = AgentOutput(output_data={"verdict": "ok", "issues": []},
                     artifact_url="", status="ok")
REPORT_OUT = AgentOutput(output_data={"summary": "s"}, artifact_url="",
                         status="ok")

REPORT_PLAN = ExecutionPlan(
    plan_id="p", nodes=[{"id": "cr", "agent": "cr_agent"},
                        {"id": "report", "agent": "report_agent"}],
    edges=[["cr", "report"]])


class _FakeEngine(HarnessEngine):
    def __init__(self, runs_root):
        super().__init__("http://127.0.0.1:1", runs_root)
        self.sent = []

    async def _send(self, node_url, agent_input, tracer, task_id_box=None,
                    budget=None):
        self.sent.append(agent_input)
        return REPORT_OUT if agent_input.node_id == "report" else CR_OUT

    async def _plan(self, trace_id, payload, tracer, context_id):
        return REPORT_PLAN


def _node_start(tid, node, agent, model="zai/glm-4.6", sha="abc123def456"):
    program = agent in ("case_executor",)
    return {"ts": 0, "trace_id": tid, "span_id": "s", "event": "node_start",
            "node_id": node,
            "payload": {"agent": agent, "upstream": {},
                        "model": "" if program else model,
                        "prompt_sha": "" if program else sha}}


def _make_run(runs, tid="t1", *, exit_code=0):
    """构造含全套产物的 run 目录（artifacts + 钉桩 trace + checkpoint）。"""
    art = runs / tid / "artifacts"
    art.mkdir(parents=True)
    (art / "cr_report.json").write_text(json.dumps({
        "issues": [{"file": "shop/pricing.py", "line": 3, "severity": "mid",
                    "type": "consistency", "desc": "阶梯与 TC-002 契约冲突"}],
        "verdict": "request_changes", "summary": "冲突需同步"}, ensure_ascii=False),
        encoding="utf-8")
    (art / "case_list.json").write_text(json.dumps({
        "case_list": [
            {"id": "TC-002", "scenario": "档位边界", "action": "reuse",
             "src": "tests/test_pricing.py::test_tier_discount",
             "linked_risk": "阶梯契约冲突"},
            {"id": "TC-101", "scenario": "新增档位精确验证", "action": "generate",
             "src": "", "linked_risk": "新阶梯"},
        ]}, ensure_ascii=False), encoding="utf-8")
    (art / "execution_report.md").write_text(
        "# 执行报告\n\n新增 50 档折扣与用例库契约冲突，需同步。", encoding="utf-8")
    events = [_node_start(tid, "cr", "cr_agent"),
              _node_start(tid, "case", "case_agent"),
              _node_start(tid, "execute", "case_executor"),
              _node_start(tid, "diagnose", "diagnose_agent"),
              _node_start(tid, "report", "report_agent")]
    (runs / tid / "trace.jsonl").write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in events) + "\n",
        encoding="utf-8")
    (runs / tid / "checkpoint.json").write_text(json.dumps({
        "run_id": tid, "context_id": "c", "current_node": None,
        "harness_state": "completed",
        "node_outputs": {
            "execute": {"status": "ok",
                        "output_data": {"exit_code": exit_code}},
            "diagnose": {"status": "ok", "output_data": {"root_causes": [
                {"case": "test_tc_002", "cause": "断言与新增阶梯冲突",
                 "evidence": "stdout"}]}},
        }}, ensure_ascii=False), encoding="utf-8")


def _fm(path):
    """手解析 frontmatter（与实现同款零依赖约定：--- 包裹 + k: v）。"""
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "---"
    end = lines.index("---", 1)
    out = {}
    for line in lines[1:end]:
        k, _, v = line.partition(":")
        out[k.strip()] = v.strip()
    return out


# ---- 纯函数：正常蒸馏 / 幂等 / 缺产物降级 / executor 失败 ----

def test_distill_writes_four_kinds_with_provenance(tmp_path):
    runs = tmp_path / "runs"
    _make_run(runs)
    corpus = tmp_path / "distilled"
    out = distill_executor.distill(runs, "t1", 1, corpus_dir=corpus)
    assert out["entries"] == 4
    assert out["by_kind"] == {"cr-issue": 1, "test-case": 1, "pattern": 1,
                              "exemplar": 1}
    issue = corpus / "cr-issue-t1-r1-1.md"
    fm = _fm(issue)
    # 矩阵 #21：frontmatter provenance 逐字段（model/prompt_sha 来自 trace 钉桩）
    assert fm["kind"] == "cr-issue"
    assert fm["source_run_id"] == "t1"
    assert fm["model"] == "zai/glm-4.6"
    assert fm["prompt_sha"] == "abc123def456"
    assert fm["round"] == "1"
    assert fm["active"] == "true"
    assert fm["quality"] == "null"
    assert "reviewed_at" in fm
    body = issue.read_text(encoding="utf-8")
    assert "阶梯与 TC-002 契约冲突" in body and "shop/pricing.py:3" in body
    # program 节点（case_executor）钉桩为空串，test-case 取 case_agent 的
    tc = corpus / "test-case-t1-r1-1.md"
    assert _fm(tc)["kind"] == "test-case"
    assert _fm(tc)["prompt_sha"] == "abc123def456"   # case_agent 的 prompt
    assert "TC-002" in tc.read_text(encoding="utf-8")
    # generate 条目不蒸馏（只有 reuse + executor 通过才沉淀）
    assert "TC-101" not in tc.read_text(encoding="utf-8")
    pat = corpus / "pattern-t1-r1-1.md"
    assert _fm(pat)["kind"] == "pattern"
    assert "断言与新增阶梯冲突" in pat.read_text(encoding="utf-8")
    # exemplar：指向 accepted 快照 + 报告要点
    ex = corpus / "exemplar-t1-r1-1.md"
    assert _fm(ex)["kind"] == "exemplar"
    assert "runs/t1/review/accepted_r1.json" in ex.read_text(encoding="utf-8")


def test_distill_idempotent_second_call_zero_entries(tmp_path):
    runs = tmp_path / "runs"
    _make_run(runs)
    corpus = tmp_path / "distilled"
    assert distill_executor.distill(runs, "t1", 1, corpus_dir=corpus)["entries"] == 4
    out = distill_executor.distill(runs, "t1", 1, corpus_dir=corpus)
    assert out["entries"] == 0
    assert len(list(corpus.glob("*.md"))) == 4


def test_distill_missing_artifacts_honest_degradation(tmp_path):  # 矩阵 #7
    runs = tmp_path / "runs"
    (runs / "t1").mkdir(parents=True)
    corpus = tmp_path / "distilled"
    out = distill_executor.distill(runs, "t1", 1, corpus_dir=corpus)
    assert out == {"entries": 0, "by_kind": {}}


def test_distill_executor_fail_skips_test_case_kind(tmp_path):
    runs = tmp_path / "runs"
    _make_run(runs, exit_code=1)   # executor 未通过 → 用例不沉淀（诚实降级）
    corpus = tmp_path / "distilled"
    out = distill_executor.distill(runs, "t1", 1, corpus_dir=corpus)
    assert out["by_kind"] == {"cr-issue": 1, "pattern": 1, "exemplar": 1}


def test_distill_writes_accepted_snapshot(tmp_path):
    runs = tmp_path / "runs"
    _make_run(runs)
    corpus = tmp_path / "distilled"
    distill_executor.distill(runs, "t1", 2, corpus_dir=corpus)
    snap = json.loads(
        (runs / "t1" / "review" / "accepted_r2.json").read_text(encoding="utf-8"))
    assert snap["round"] == 2
    assert snap["provenance"]["model"] == "zai/glm-4.6"
    assert "执行报告" in snap["report_md"]


# ---- engine 接线：accept 后蒸馏 / 失败不阻断（矩阵 #8） ----

def _events(runs, tid):
    return [json.loads(line) for line in
            (runs / tid / "trace.jsonl").read_text().splitlines()]


async def test_engine_accept_distills(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_INFRA_REVIEW_AUTO", "1")   # auto 也是 accept
    runs = tmp_path / "runs"
    _make_run(runs)
    engine = _FakeEngine(runs)
    engine.distill_corpus_dir = tmp_path / "distilled"
    await engine.execute_for("t1", {})
    corpus = tmp_path / "distilled"
    # fake 链只产 cr/report 产物（engine 落盘 checkpoint 覆盖 fixture）——
    # 可蒸馏的如实是 cr-issue 1 + exemplar 1（test-case/pattern 无源降级）
    assert len(list(corpus.glob("*.md"))) == 2
    events = _events(runs, "t1")
    assert any(e["event"] == "distill_end" and e["payload"]["entries"] == 2
               for e in events)
    # 状态收尾：completed（auto accept 直落）
    cp = json.loads((runs / "t1" / "checkpoint.json").read_text())
    assert cp["harness_state"] == "completed"


async def test_engine_manual_accept_distills(tmp_path, monkeypatch):
    runs = tmp_path / "runs"
    _make_run(runs)
    engine = _FakeEngine(runs)
    engine.distill_corpus_dir = tmp_path / "distilled"
    task = asyncio.create_task(engine.execute_for("t1", {}))
    deadline = asyncio.get_running_loop().time() + 2.0
    while True:   # 等 run 进 review_pending
        h = engine._runs.get("t1")
        if h and h.review_event is not None and not h.review_event.is_set():
            break
        if asyncio.get_running_loop().time() > deadline:
            raise TimeoutError("not in review pending")
        await asyncio.sleep(0.01)
    assert engine.review_run("t1", "accept", "")
    await task
    assert len(list((tmp_path / "distilled").glob("*.md"))) == 2
    assert any(e["event"] == "review_accepted"
               for e in _events(runs, "t1"))


async def test_engine_distill_failure_does_not_block(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_INFRA_REVIEW_AUTO", "1")
    runs = tmp_path / "runs"
    engine = _FakeEngine(runs)
    engine.distill_corpus_dir = tmp_path / "distilled"

    def _boom(*a, **kw):
        raise OSError("disk full")
    monkeypatch.setattr(distill_executor, "distill", _boom)
    await engine.execute_for("t1", {})
    events = _events(runs, "t1")
    assert any(e["event"] == "distill_failed" and "disk full" in e["payload"]["error"]
               for e in events)                       # 矩阵 #8
    cp = json.loads((runs / "t1" / "checkpoint.json").read_text())
    assert cp["harness_state"] == "completed"          # 不阻断 COMPLETED


@pytest.fixture(autouse=True)
def _no_default_corpus(monkeypatch, tmp_path):
    """防误写仓库语料：默认语料目录指到 tmp（engine 未注入 corpus_dir 时兜底）。"""
    monkeypatch.setattr(distill_executor, "_CORPUS_DEFAULT",
                        tmp_path / "unused-distilled")


def test_distill_round2_entries_independent(tmp_path):
    """t6-rev Important#2 回归：replan 多轮——round2 条目不被 round1 同名
    幂等跳过，provenance 取当轮（最后一次 node_start）钉桩。

    修复前文件名不掺 round：round1 的 cr-issue-t1-1.md 已存在 → round2
    的认可结论静默丢失（exemplar 还钉着 r1 快照指引）。"""
    import json as _json

    runs = tmp_path / "runs"
    _make_run(runs)
    corpus = tmp_path / "distilled"
    assert distill_executor.distill(runs, "t1", 1, corpus_dir=corpus)["entries"] == 4
    # round2：追加第二轮 node_start（模型/prompt 换版本——replan 换模型是真实面）
    trace = runs / "t1" / "trace.jsonl"
    r2 = [_node_start("t1", "cr", "cr_agent", model="zai/glm-5.3",
                      sha="fff000fff000")]
    trace.write_text(trace.read_text(encoding="utf-8") + "".join(
        _json.dumps(e, ensure_ascii=False) + "\n" for e in r2),
        encoding="utf-8")
    out2 = distill_executor.distill(runs, "t1", 2, corpus_dir=corpus)
    assert out2["entries"] == 4                       # round2 全量独立落盘
    r2_issue = corpus / "cr-issue-t1-r2-1.md"
    assert r2_issue.exists()                          # 不被 r1 同名跳过
    assert _fm(r2_issue)["model"] == "zai/glm-5.3"    # provenance=当轮钉桩
    assert _fm(r2_issue)["round"] == "2"
    r1_issue = corpus / "cr-issue-t1-r1-1.md"
    assert _fm(r1_issue)["model"] == "zai/glm-4.6"    # r1 不被 r2 污染
    assert _fm(corpus / "exemplar-t1-r2-1.md")["kind"] == "exemplar"
    assert "accepted_r2.json" in (corpus / "exemplar-t1-r2-1.md").read_text(
        encoding="utf-8")
