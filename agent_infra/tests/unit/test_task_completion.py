"""task_completion scorer 单测：cr_hit 复用 + plan_match 集合比 + N/A 语义。

覆盖矩阵 #4（plan 缺失 N/A、e2e_done 照记）/#5（executor 无执行证据 0 分计
分母——test_cover 是存在性语义：checkpoint 含 exit_code 即执行过）。
"""
import json

import pytest

from eval.evaluate import load_golden
from eval.task_completion import aggregate_task_completion, score_task_completion

G1 = load_golden()["defect-1"]
HIT_REPORT = {"issues": [dict(g, desc="x") for g in G1["issues"]],
              "verdict": G1["verdict"], "summary": "s"}   # 位置全命中 + verdict 对
PLAN_DEFAULT = {"plan_id": "P",
                "nodes": [{"id": "cr", "agent": "cr_agent"},
                          {"id": "tr", "agent": "test_recall_agent"},
                          {"id": "chr", "agent": "change_report_agent"},
                          {"id": "case", "agent": "case_agent"},
                          {"id": "script", "agent": "script_agent"},
                          {"id": "e", "program": "case_executor"},
                          {"id": "r", "agent": "report_agent"}],
                "edges": [["req", "str"], ["str", "cr"], ["cr", "tr"],
                          ["tr", "chr"], ["chr", "case"], ["case", "script"],
                          ["script", "e"], ["e", "r"]]}
TRACE_OK = [
    {"event": "run_start", "node_id": None, "payload": {"commit": "defect-1"}},
    {"event": "node_start", "node_id": "cr",
     "payload": {"agent": "cr_agent", "upstream": {}}},
    {"event": "node_end", "node_id": "cr", "payload": {"status": "ok"}},
    {"event": "run_end", "node_id": None, "payload": {"status": "ok"}},
]


def _mk_run(tmp_path, *, events=TRACE_OK, files=None):
    run = tmp_path / "r1"
    (run / "artifacts").mkdir(parents=True, exist_ok=True)  # 同 tmp_path 二次调用
    run.joinpath("trace.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events),
        encoding="utf-8")
    for rel, text in (files or {}).items():
        p = run / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return run


CHECKPOINT_FULL = json.dumps({  # executor 真执行过：execute 节点 output_data 含 exit_code
    "run_id": "r1", "context_id": "r1", "current_node": None,
    "harness_state": "executing", "completed_nodes": ["cr", "testing", "execute"],
    "node_outputs": {
        "cr": {"status": "ok", "output_data": {}, "artifacts": []},
        "testing": {"status": "ok", "output_data": {}, "artifacts": []},
        "execute": {"status": "ok",
                    "output_data": {"exit_code": 1, "stdout": "FFF", "stderr": ""},
                    "artifacts": []}},
    "version": 1, "created_at": 0}, ensure_ascii=False)

FULL_FILES = {"artifacts/cr_report.json": json.dumps(HIT_REPORT, ensure_ascii=False),
              "artifacts/plan.json": json.dumps(PLAN_DEFAULT, ensure_ascii=False),
              "checkpoint.json": CHECKPOINT_FULL}


def test_full_run_scores_full_marks(tmp_path):
    r = score_task_completion(G1, _mk_run(tmp_path, files=FULL_FILES))
    assert r["cr_hit"] == 1.0 and r["verdict_ok"] is True
    assert r["plan_match"] == 1.0 and r["test_cover"] == 1.0
    assert r["e2e_done"] is True and r["notes"] == []


def test_exec_exit_code_recorded_but_not_scored(tmp_path):
    # exit_code 数值只进 report：跑失败（exit_code=1）也是「产了用例并执行」
    r = score_task_completion(G1, _mk_run(tmp_path, files=FULL_FILES))
    assert r["exec_exit_code"] == 1 and r["test_cover"] == 1.0
    cp = json.loads(CHECKPOINT_FULL)
    cp["node_outputs"]["execute"]["output_data"]["exit_code"] = 0
    r2 = score_task_completion(G1, _mk_run(
        tmp_path, files={**FULL_FILES, "checkpoint.json": json.dumps(cp)}))
    assert r2["exec_exit_code"] == 0 and r2["test_cover"] == 1.0


def test_missing_cr_report_scores_zero_with_note(tmp_path):
    r = score_task_completion(G1, _mk_run(
        tmp_path, files={"artifacts/plan.json": json.dumps(PLAN_DEFAULT),
                         "checkpoint.json": CHECKPOINT_FULL}))
    assert r["cr_hit"] == 0.0 and r["verdict_ok"] is False
    assert "missing cr_report.json" in r["notes"]


def test_plan_match_jaccard_and_golden_shape(tmp_path):
    extra = dict(PLAN_DEFAULT)
    extra["nodes"] = PLAN_DEFAULT["nodes"] + [
        {"id": "diag", "agent": "diagnose_agent"}]   # 7 节点默认链外多选 → 降分
    r = score_task_completion(G1, _mk_run(
        tmp_path, files={**FULL_FILES,
                         "artifacts/plan.json": json.dumps(extra)}))
    assert r["plan_match"] == pytest.approx(7 / 8)  # |∩|=7 / |∪|=8
    for tag, entry in load_golden().items():   # golden 形状钉桩
        assert entry["expect_nodes"] and entry["expect_test"] is True, tag


def test_plan_missing_is_na_but_e2e_done_recorded(tmp_path):  # 矩阵 #4
    r = score_task_completion(G1, _mk_run(
        tmp_path, files={"artifacts/cr_report.json":
                         json.dumps(HIT_REPORT)}))
    assert r["plan_match"] is None          # N/A 不计分母
    assert r["e2e_done"] is True            # 照记，不受 plan 缺失影响
    no_end = [e for e in TRACE_OK if e["event"] != "run_end"]
    r2 = score_task_completion(G1, _mk_run(tmp_path, events=no_end))
    assert r2["e2e_done"] is False          # 无 run_end 如实 False


def test_test_cover_no_executor_evidence_zero(tmp_path):  # 矩阵 #5
    r = score_task_completion(G1, _mk_run(
        tmp_path, files={"artifacts/cr_report.json":
                         json.dumps(HIT_REPORT)}))
    assert r["test_cover"] == 0.0           # 无 checkpoint = 0 分且计分母（不是 None）
    assert r["exec_exit_code"] is None
    # checkpoint 存在但没有任何节点产出 exit_code（executor 未真跑）→ 同样 0 分
    no_exec = json.loads(CHECKPOINT_FULL)
    del no_exec["node_outputs"]["execute"]
    r2 = score_task_completion(G1, _mk_run(
        tmp_path, files={"checkpoint.json": json.dumps(no_exec)}))
    assert r2["test_cover"] == 0.0


def test_aggregate_skips_na():
    per = {"defect-1": {"cr_hit": 1.0, "verdict_ok": True, "plan_match": None,
                        "test_cover": 1.0, "e2e_done": True},
           "defect-2": {"cr_hit": 0.0, "verdict_ok": False, "plan_match": 0.5,
                        "test_cover": 0.0, "e2e_done": False}}
    agg = aggregate_task_completion(per)
    assert agg["cr_hit"] == 0.5
    assert agg["plan_match"] == 0.5         # 只对非 None 平均
    assert agg["e2e_done"] == 0.5
    all_na = {k: dict(v, plan_match=None) for k, v in per.items()}
    assert aggregate_task_completion(all_na)["plan_match"] is None
