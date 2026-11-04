"""九期 Task 8：质量打分器（裁定 A/B/C）+ engine accept 路径挂分。

零真实 LLM：judge complete 全注入 fake，rubric prompt 只验证结构（回音室防线①
文案钉桩）。硬维度机械校验用临时 git 仓构造（不依赖 fixture repo 存在）。
"""
import asyncio
import json
import subprocess

import pytest

from eval.quality import (
    EXEMPLAR_MIN_QUALITY,
    JUDGE_VERSION,
    score_evidence,
    score_report,
)
from harness.contract import AgentOutput, ExecutionPlan
from harness.engine import HarnessEngine

CR_OUT = AgentOutput(output_data={"verdict": "ok", "issues": []},
                     artifact_url="", status="ok")
REPORT_OUT = AgentOutput(output_data={"summary": "s"}, artifact_url="",
                         status="ok")
REPORT_PLAN = ExecutionPlan(
    plan_id="p", nodes=[{"id": "cr", "agent": "cr_agent"},
                        {"id": "report", "agent": "report_agent"}],
    edges=[["cr", "report"]])


class _FakeEngine(HarnessEngine):
    """in-proc fake：绕过 A2A（与 test_engine_review 同手法）。"""

    def __init__(self, runs_root):
        super().__init__("http://127.0.0.1:1", runs_root)

    async def _send(self, node_url, agent_input, tracer, task_id_box=None,
                    budget=None):
        return REPORT_OUT if agent_input.node_id == "report_agent" else CR_OUT


async def _wait_review(engine, trace_id, timeout=2.0):
    """等 review_event 已建未 set（排除上一轮已 set 未消费的旧事件）。"""
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


def _git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "shop").mkdir()
    (repo / "shop" / "pricing.py").write_text("a = 1\nb = 2\nc = 3\n",
                                              encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    subprocess.run(["git", "-C", str(repo), "-c", "user.email=t@t",
                    "-c", "user.name=t", "commit", "-qm", "init"], check=True)
    return repo


def _issue(file="shop/pricing.py", line=2):
    return {"file": file, "line": line, "severity": "mid", "type": "x",
            "desc": "d"}


def test_evidence_mechanical(tmp_path):
    """#21d：硬维度纯机械——file 在 commit 里且 line 在行数内才得分。"""
    repo = _git_repo(tmp_path)
    assert score_evidence([_issue()], str(repo), "HEAD") == 1.0
    # file 不存在 + line 越界 → 两条全 0（记 0 分条目）
    assert score_evidence([_issue(file="shop/nope.py"), _issue(line=99)],
                          str(repo), "HEAD") == 0.0
    # 一半命中
    assert score_evidence([_issue(), _issue(file="shop/nope.py")],
                          str(repo), "HEAD") == 0.5


def test_evidence_empty_issues_is_zero(tmp_path):
    assert score_evidence([], str(_git_repo(tmp_path)), "HEAD") == 0.0


def test_score_report_hard_only_and_judge_version(tmp_path):
    """complete=None → 软维度 None、total 只计硬维度（benchmark 用，裁定 B）；
    judge 版本常量钉进结果（换 judge=基线申报，不许静默）。"""
    repo = _git_repo(tmp_path)
    out = score_report({"issues": [_issue()]}, str(repo), "HEAD")
    assert out["judge_version"] == JUDGE_VERSION
    assert out["evidence"] == 1.0
    assert out["coverage"] is None
    assert out["consistency"] is None
    assert out["readability"] is None
    assert out["total"] == 1.0


def test_soft_dims_via_injected_complete(tmp_path):
    """complete 注入 → 软维度解析 + total 四维均值；prompt 验证结构（不烧 LLM）"""
    repo = _git_repo(tmp_path)
    seen = {}

    def fake_complete(prompt):
        seen["prompt"] = prompt
        return json.dumps({"coverage": 0.8, "consistency": 0.6,
                           "readability": 1.0})

    out = score_report({"issues": [_issue()]}, str(repo), "HEAD",
                       complete=fake_complete)
    assert (out["coverage"], out["consistency"], out["readability"]) == \
        (0.8, 0.6, 1.0)
    assert out["total"] == pytest.approx((1.0 + 0.8 + 0.6 + 1.0) / 4)
    # 回音室防线①进 prompt 文本：度量绝对质量，不度量与范例的相似度
    assert "相似度" in seen["prompt"] and "范例" in seen["prompt"]
    assert "绝对" in seen["prompt"]


def _exemplar(path, run_id, quality="null", active="true"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nkind: exemplar\nsource_run_id: {run_id}\nmodel: zai/glm-4.6\n"
        f"prompt_sha: abc123def456\nround: 1\nreviewed_at: 2026-01-01\n"
        f"active: {active}\nquality: {quality}\n---\n\n正文\n", encoding="utf-8")


def _run_with_report(runs, tid, verdict):
    art = runs / tid / "artifacts"
    art.mkdir(parents=True, exist_ok=True)
    (art / "cr_report.json").write_text(json.dumps(
        {"issues": [], "verdict": verdict, "summary": verdict}),
        encoding="utf-8")


def test_backfill_gates_low_quality(tmp_path):
    """#21e：低分 exemplar active:false（只翻标志不删文件，审计保留）；
    高分回填 quality；阈值常量 0.6（可调，回填判定即其消费点）。"""
    from eval.quality import backfill_quality
    runs = tmp_path / "runs"
    _run_with_report(runs, "t-good", "good")
    _run_with_report(runs, "t-bad", "bad")
    corpus = tmp_path / "distilled"
    _exemplar(corpus / "exemplar-t-good-r1-1.md", "t-good")
    _exemplar(corpus / "exemplar-t-bad-r1-1.md", "t-bad")

    def fake_scorer(report, repo, commit):
        return {"total": 0.9 if report["verdict"] == "good" else 0.2,
                "judge_version": JUDGE_VERSION}

    out = backfill_quality(corpus, runs, "repo", scorer=fake_scorer)
    assert EXEMPLAR_MIN_QUALITY == 0.6
    assert out["backfilled"] == 2 and out["gated"] == 1
    good = (corpus / "exemplar-t-good-r1-1.md").read_text(encoding="utf-8")
    bad = (corpus / "exemplar-t-bad-r1-1.md").read_text(encoding="utf-8")
    assert "quality: 0.9" in good and "active: true" in good
    assert "quality: 0.2" in bad and "active: false" in bad
    assert (corpus / "exemplar-t-bad-r1-1.md").exists()   # 不删文件


def test_backfill_idempotent(tmp_path):
    """已有 quality 的条目跳过（二次调用零改动）。"""
    from eval.quality import backfill_quality
    runs = tmp_path / "runs"
    _run_with_report(runs, "t1", "good")
    corpus = tmp_path / "distilled"
    _exemplar(corpus / "exemplar-t1-r1-1.md", "t1")
    scorer = lambda report, repo, commit: {"total": 0.9}  # noqa: E731
    backfill_quality(corpus, runs, "repo", scorer=scorer)
    mtime = (corpus / "exemplar-t1-r1-1.md").stat().st_mtime
    out = backfill_quality(corpus, runs, "repo", scorer=scorer)
    assert out["backfilled"] == 0
    assert (corpus / "exemplar-t1-r1-1.md").stat().st_mtime == mtime


async def test_accept_payload_carries_quality(tmp_path):
    """裁定 A：手动 accept 路径——打分失败/成功都挂进 review_accepted payload，
    scorer 抛异常置 None 不阻断 COMPLETED。"""
    runs = tmp_path / "runs"
    engine = _FakeEngine(runs)
    (runs / "t1" / "artifacts").mkdir(parents=True)
    (runs / "t1" / "artifacts" / "cr_report.json").write_text(
        json.dumps({"issues": []}), encoding="utf-8")
    engine.quality_scorer = lambda report, repo, commit: {
        "evidence": 1.0, "judge_version": JUDGE_VERSION}
    task = asyncio.create_task(engine.execute_for("t1", {"repo": "x"},
                                                  REPORT_PLAN))
    await _wait_review(engine, "t1")
    engine.review_run("t1", "accept")
    await task
    ev = next(e for e in _events(runs, "t1")
              if e["event"] == "review_accepted")
    assert ev["payload"]["quality"]["judge_version"] == JUDGE_VERSION

    # scorer 抛异常 → quality=None，run 仍 COMPLETED
    engine2 = _FakeEngine(runs)
    (runs / "t2" / "artifacts").mkdir(parents=True)
    (runs / "t2" / "artifacts" / "cr_report.json").write_text(
        json.dumps({"issues": []}), encoding="utf-8")
    engine2.quality_scorer = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("judge down"))
    task = asyncio.create_task(engine2.execute_for("t2", {"repo": "x"},
                                                   REPORT_PLAN))
    await _wait_review(engine2, "t2")
    engine2.review_run("t2", "accept")
    await task
    ev = next(e for e in _events(runs, "t2")
              if e["event"] == "review_accepted")
    assert ev["payload"]["quality"] is None
    cp = json.loads((runs / "t2" / "checkpoint.json").read_text())
    assert cp["harness_state"] == "completed"


async def test_auto_path_never_scores(tmp_path, monkeypatch):
    """裁定 A：REVIEW_AUTO 无人值守路径不打分（评测不烧 judge token）。"""
    monkeypatch.setenv("AGENT_INFRA_REVIEW_AUTO", "1")
    calls = []

    def spy(report, repo, commit):
        calls.append(report)
        return {"total": 1.0}

    runs = tmp_path / "runs"
    engine = _FakeEngine(runs)
    engine.quality_scorer = spy
    await engine.execute_for("t3", {"repo": "x"}, REPORT_PLAN)
    assert calls == []
    ev = next(e for e in _events(runs, "t3")
              if e["event"] == "review_auto_accepted")
    assert "quality" not in ev["payload"]


def test_rewrite_fm_inserts_missing_keys(tmp_path):
    """t8-rev Minor 回归：_rewrite_fm 对缺失键插入而非静默丢（伪幂等）。"""
    from eval.quality import _rewrite_fm
    f = tmp_path / "hand.md"
    f.write_text("---\nkind: exemplar\nactive: true\n---\n\n正文\n",
                 encoding="utf-8")
    _rewrite_fm(f, {"quality": "0.8", "active": "false"})
    fm = {}
    lines = f.read_text(encoding="utf-8").splitlines()
    end = lines.index("---", 1)
    for line in lines[1:end]:
        k, _, v = line.partition(":")
        fm[k.strip()] = v.strip()
    assert fm["quality"] == "0.8"          # 缺失键被插入（不被静默丢）
    assert fm["active"] == "false"          # 已有键照改
    assert lines[end + 1] == ""             # 正文区不受插行影响
