"""集成：benchmark 编排器——离线收集/基线/漂移门禁/异常隔离（矩阵 #6-#9/#13/#14）
+ 终审修正（C1 覆盖 fail-closed / I1 拒写坏基线 / I3 陈旧 run 选择 / M2 单 run 分数路径）。

合成 run 直写 trace.jsonl（含 Task 1 的 node_start agent/upstream payload）与
artifacts，不打引擎不烧 LLM；成功路径不 SystemExit，失败路径断言退出码。
"""
import json
import os
import shutil

import pytest

import eval.benchmark as bm
from eval.benchmark import main

GOLDEN = bm.load_golden()


def _mk_run(root, tag, *, deny=False, with_cr=True, with_plan=True,
            with_test=True, dirname=None):
    """合成一个满分的单 defect run（deny=True 时注入一次越权拒绝）。"""
    d = root / (dirname or f"{tag}-run")
    (d / "artifacts").mkdir(parents=True)
    events = [
        {"event": "run_start", "node_id": None, "payload": {"commit": tag}},
        {"event": "node_start", "node_id": "cr",
         "payload": {"agent": "cr_agent", "upstream": {}}},
        {"event": "llm_call", "node_id": None, "payload": {"turn": 1}},
        {"event": "tool_call", "node_id": None, "payload": {"tool": "read_diff"}},
    ]
    if deny:
        events += [
            {"event": "tool_call", "node_id": None,
             "payload": {"tool": "run_cmd"}},
            {"event": "policy_deny", "node_id": None,
             "payload": {"where": "before_tool",
                         "reason": "tool not allowed: run_cmd"}}]
    events += [
        {"event": "node_end", "node_id": "cr", "payload": {"status": "ok"}},
        {"event": "node_start", "node_id": "test_recall",
         "payload": {"agent": "test_recall_agent", "upstream": {}}},
        {"event": "tool_call", "node_id": None,
         "payload": {"tool": "search_knowledge"}},
        {"event": "node_end", "node_id": "test_recall",
         "payload": {"status": "ok"}},
        {"event": "node_start", "node_id": "case",
         "payload": {"agent": "case_agent", "upstream": {}}},
        {"event": "tool_call", "node_id": None,
         "payload": {"tool": "read_artifact"}},
        {"event": "node_end", "node_id": "case", "payload": {"status": "ok"}},
        {"event": "node_start", "node_id": "script",
         "payload": {"agent": "script_agent", "upstream": {}}},
        {"event": "tool_call", "node_id": None,
         "payload": {"tool": "read_artifact"}},
        {"event": "tool_call", "node_id": None,
         "payload": {"tool": "write_file"}},
        {"event": "node_end", "node_id": "script", "payload": {"status": "ok"}},
        {"event": "node_start", "node_id": "report",
         "payload": {"agent": "report_agent", "upstream": {}}},
        {"event": "tool_call", "node_id": None,
         "payload": {"tool": "read_artifact"}},
        {"event": "node_end", "node_id": "report", "payload": {"status": "ok"}},
        {"event": "run_end", "node_id": None, "payload": {"status": "ok"}},
    ]
    d.joinpath("trace.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events),
        encoding="utf-8")
    if with_cr:
        g = GOLDEN[tag]
        (d / "artifacts" / "cr_report.json").write_text(json.dumps(
            {"issues": [dict(i, desc="x") for i in g["issues"]],
             "verdict": g["verdict"], "summary": "s"}, ensure_ascii=False),
            encoding="utf-8")
    if with_plan:
        (d / "artifacts" / "plan.json").write_text(json.dumps(
            {"plan_id": "P",
             "nodes": [{"id": "cr", "agent": "cr_agent"},
                       {"id": "tr", "agent": "test_recall_agent"},
                       {"id": "case", "agent": "case_agent"},
                       {"id": "script", "agent": "script_agent"},
                       {"id": "e", "program": "case_executor"},
                       {"id": "r", "agent": "report_agent"}],
             "edges": [["cr", "tr"], ["tr", "case"], ["case", "script"],
                       ["script", "e"], ["e", "r"]]}, ensure_ascii=False),
            encoding="utf-8")
    if with_test:
        # test_cover 契约（C 系修正）：executor 真执行过的证据是 checkpoint 的
        # execute 节点 output_data 含 exit_code，不是瞬态的 sandbox/test_cases.py
        (d / "checkpoint.json").write_text(json.dumps({
            "run_id": d.name, "context_id": d.name, "current_node": None,
            "harness_state": "executing",
            "completed_nodes": ["cr", "test_recall", "case", "script",
                                "execute", "report"],
            "node_outputs": {"execute": {"status": "ok", "output_data": {
                "exit_code": 1, "stdout": "", "stderr": ""}, "artifacts": []}},
            "version": 1, "created_at": 0}, ensure_ascii=False), encoding="utf-8")
    return d


def _patch_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(bm, "BASELINE_PATH", tmp_path / "baseline.json")
    monkeypatch.setattr(bm, "SCORES_PATH", tmp_path / "scores.json")


def _full_root(tmp_path):
    root = tmp_path / "runs"
    for tag in GOLDEN:
        _mk_run(root, tag)
    return root


def test_offline_missing_dir_exits_2(tmp_path, capsys):  # 矩阵 #6
    with pytest.raises(SystemExit) as ei:
        main(["--from", str(tmp_path / "nope")])
    assert ei.value.code == 2
    assert "不存在" in capsys.readouterr().out


def test_first_run_without_baseline_exits_0_with_guidance(  # 矩阵 #7
        tmp_path, monkeypatch, capsys):
    _patch_paths(monkeypatch, tmp_path)
    main(["--from", str(_full_root(tmp_path))])     # 成功路径不 SystemExit
    out = capsys.readouterr().out
    assert "建基线" in out and "eval-update" in out
    scores = json.loads((tmp_path / "scores.json").read_text(encoding="utf-8"))
    assert scores["baseline"] == {"exists": False, "gated": False, "drift": []}
    assert scores["metrics"]["tool_calling"]["legality"] == 1.0


def test_scorer_exception_isolated(tmp_path, monkeypatch, capsys):  # 矩阵 #8
    _patch_paths(monkeypatch, tmp_path)
    real = bm.score_task_completion

    def flaky(entry, run_dir):
        if run_dir.name == "defect-3-run":
            raise RuntimeError("boom")
        return real(entry, run_dir)

    monkeypatch.setattr(bm, "score_task_completion", flaky)
    with pytest.raises(SystemExit) as ei:
        main(["--from", str(_full_root(tmp_path))])
    assert ei.value.code == 1                        # 有 error 行 → exit 1
    out = capsys.readouterr().out
    assert "defect-3: ERROR" in out and "defect-1:" in out   # 其余照评


async def test_run_online_continues_after_defect_failure(  # 矩阵 #9
        tmp_path, monkeypatch):
    monkeypatch.setattr(bm, "runs_root", lambda: tmp_path / "rr")
    runs = tmp_path / "rr"

    class FakeEngine:
        """run_online 会先 rmtree 清残留——正常 defect 在 execute_for 里
        重建 run 目录（模拟真实产出），defect-3 三次重试全挂不产出。"""

        def __init__(self):
            self.calls = []

        async def execute_for(self, trace_id, payload):
            self.calls.append(payload["commit"])
            if payload["commit"] == "defect-3":
                raise RuntimeError("retries exhausted")
            return _mk_run(runs, payload["commit"], dirname=trace_id)

    fake = FakeEngine()
    dirs = await bm.run_online(GOLDEN, engine=fake)
    assert len(fake.calls) == len(GOLDEN)            # 失败不中断其余 defect
    assert set(dirs) == set(GOLDEN)
    rows, had_error = bm.score_defects(GOLDEN, dirs)
    assert had_error and "error" in rows["defect-3"]  # 目录未产出 → 响亮 error 行
    assert "error" not in rows["defect-1"]


def test_drift_exit_1_names_metric(tmp_path, monkeypatch, capsys):  # 矩阵 #13
    _patch_paths(monkeypatch, tmp_path)
    root = tmp_path / "runs"
    for tag in GOLDEN:
        _mk_run(root, tag, deny=True)                # legality 0.75
    bm.write_baseline({"tool_calling": {"legality": 1.0, "must_use_hit": 1.0},
                       "task_completion": {"cr_hit": 1.0}}, "test")
    with pytest.raises(SystemExit) as ei:
        main(["--from", str(root)])
    assert ei.value.code == 1
    out = capsys.readouterr().out
    assert "基准漂移" in out and "tool_calling.legality" in out   # 点名指标


def test_update_baseline_then_pass(tmp_path, monkeypatch, capsys):  # 矩阵 #14
    _patch_paths(monkeypatch, tmp_path)
    root = _full_root(tmp_path)
    main(["--from", str(root), "--update-baseline"])  # 写基线，exit 0
    data = json.loads((tmp_path / "baseline.json").read_text(encoding="utf-8"))
    assert data["source"].startswith("offline:") and data["generated_at"]
    assert data["metrics"]["tool_calling"]["legality"] == 1.0
    assert data["metrics"]["n_defects"] == len(GOLDEN)       # I4：口径入基线
    assert set(data["metrics"]["per_defect"]) == set(GOLDEN)  # I4：逐 defect 可查
    main(["--from", str(root)])                       # 新基线生效 → 门禁通过
    assert "门禁通过" in capsys.readouterr().out


def test_from_file_exits_2(tmp_path, monkeypatch, capsys):  # M1
    _patch_paths(monkeypatch, tmp_path)
    f = tmp_path / "trace.jsonl"
    f.write_text("not a dir\n", encoding="utf-8")
    with pytest.raises(SystemExit) as ei:
        main(["--from", str(f)])
    assert ei.value.code == 2
    assert "文件" in capsys.readouterr().out


def test_gated_partial_coverage_exits_1_with_missing_list(  # C1
        tmp_path, monkeypatch, capsys):
    _patch_paths(monkeypatch, tmp_path)
    root = _full_root(tmp_path)
    main(["--from", str(root), "--update-baseline"])  # 全量 run 建基线
    keep = {f"{t}-run" for t in list(GOLDEN)[:2]}
    for d in root.iterdir():                          # 删到只剩 2 个 run
        if d.name not in keep:
            shutil.rmtree(d)
    with pytest.raises(SystemExit) as ei:
        main(["--from", str(root)])
    assert ei.value.code == 1                         # 不再按 2-defect 子集放行
    missing = sorted(set(GOLDEN) - set(list(GOLDEN)[:2]))
    out = capsys.readouterr().out
    assert "覆盖不全" in out and all(m in out for m in missing)


def test_update_baseline_refuses_partial_run(tmp_path, monkeypatch, capsys):  # I1
    _patch_paths(monkeypatch, tmp_path)
    root = tmp_path / "runs"
    for tag in list(GOLDEN)[:2]:
        _mk_run(root, tag)
    with pytest.raises(SystemExit) as ei:
        main(["--from", str(root), "--update-baseline"])
    assert ei.value.code == 1
    assert "拒绝写基线" in capsys.readouterr().out
    assert not (tmp_path / "baseline.json").exists()  # 根信任未被污染


def test_update_baseline_refuses_error_run(tmp_path, monkeypatch, capsys):  # I1
    _patch_paths(monkeypatch, tmp_path)
    real = bm.score_task_completion

    def flaky(entry, run_dir):
        if run_dir.name == "defect-3-run":
            raise RuntimeError("boom")
        return real(entry, run_dir)

    monkeypatch.setattr(bm, "score_task_completion", flaky)
    with pytest.raises(SystemExit) as ei:
        main(["--from", str(_full_root(tmp_path)), "--update-baseline"])
    assert ei.value.code == 1
    assert "拒绝写基线" in capsys.readouterr().out
    assert not (tmp_path / "baseline.json").exists()


def test_collect_prefers_bench_prefix_over_newer_mtime(tmp_path, capsys):  # I3
    root = tmp_path / "runs"
    old = _mk_run(root, "defect-1", dirname="bench-defect-1")
    new = _mk_run(root, "defect-1", dirname="defect-1-run")
    os.utime(old / "trace.jsonl", (1_000_000, 1_000_000))   # bench- 更旧
    os.utime(new / "trace.jsonl", (2_000_000, 2_000_000))
    runs, single = bm.collect_offline(root)
    assert not single and runs["defect-1"] == old      # bench- 前缀压过新 mtime
    assert "选中 run bench-defect-1" in capsys.readouterr().out


def test_collect_non_bench_falls_back_to_latest_mtime(tmp_path):  # I3
    root = tmp_path / "runs"
    stale = _mk_run(root, "defect-1", dirname="a-defect-1")
    fresh = _mk_run(root, "defect-1", dirname="z-defect-1")
    os.utime(stale / "trace.jsonl", (1_000_000, 1_000_000))
    os.utime(fresh / "trace.jsonl", (2_000_000, 2_000_000))
    runs, _ = bm.collect_offline(root)
    assert runs["defect-1"] == fresh                   # 无 bench- → mtime 最新


def test_single_run_writes_scores_into_run_dir(  # M2
        tmp_path, monkeypatch, capsys):
    _patch_paths(monkeypatch, tmp_path)
    d = _mk_run(tmp_path, "defect-1")
    main(["--from", str(d)])
    assert "单 run 报告模式" in capsys.readouterr().out
    scores = json.loads((d / "scores.json").read_text(encoding="utf-8"))
    assert scores["metrics"]["n_defects"] == 1
    assert not (tmp_path / "scores.json").exists()     # 门禁 scores 未被覆写
