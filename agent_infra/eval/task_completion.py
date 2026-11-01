"""V 层：Task Completion 评测——golden + 产物/trace → 完成度分数（纯离线）。

cr_hit/verdict_ok 复用 eval.evaluate.evaluate_commit（既有 CR 打分不重写，
设计 §0）；plan_match 按 plan.json 的 registry 名集合与 golden expect_nodes
做 Jaccard（设计 §4：全链/短链都合法，全序比对被否决；边一致性由执行结果
兜底——拓扑错的 plan 跑不出 ok 的 run_end）；test_cover 看 executor 是否真
执行过脚本——存在性语义：checkpoint.json 的 node_outputs.<execute>.output_data
含 exit_code 即「产了用例并执行」（矩阵 #5：缺执行证据是完成度事实，0 分计
分母；exit_code 数值只进 report 不改分——跑失败也是执行了）；e2e_done 看最后
一个 run_end 事件状态（矩阵 #4：plan.json 缺失不影响 e2e_done 照记）。
"""
from __future__ import annotations

import json
from pathlib import Path

from eval.evaluate import evaluate_commit
from eval.tool_calling import load_trace


def _executor_exit_code(run_dir: Path) -> int | None:
    """executor 真执行过的持久证据：checkpoint 某节点 output_data 含 exit_code。

    锚点键 execute（planning prompt 约定的局部 id）；其他局部 id（如 exec）
    兜底扫描——判定依据是「有节点产出了 exit_code」，而非瞬态脚本存在。
    """
    cp_file = Path(run_dir) / "checkpoint.json"
    if not cp_file.exists():
        return None
    outs = json.loads(cp_file.read_text(encoding="utf-8")).get("node_outputs", {})
    ordered = [outs[k] for k in ("execute",) if k in outs] + [
        v for k, v in outs.items() if k != "execute"]
    for v in ordered:
        data = v.get("output_data") if isinstance(v, dict) else None
        if isinstance(data, dict) and "exit_code" in data:
            return data["exit_code"]
    return None


def score_task_completion(golden_entry: dict, run_dir: Path) -> dict:
    """单 defect 完成度：cr_hit/verdict_ok/plan_match/test_cover/e2e_done。"""
    run_dir = Path(run_dir)
    notes: list[str] = []
    # cr_hit：复用既有 CR 打分；cr_report.json 缺失按空报告计（0 命中）+ 标注
    report_file = run_dir / "artifacts" / "cr_report.json"
    if report_file.exists():
        report = json.loads(report_file.read_text(encoding="utf-8"))
    else:
        report = {}
        notes.append("missing cr_report.json")
    r = evaluate_commit(golden_entry, report)
    total = r["hits"] + r["misses"]
    cr_hit = r["hits"] / total if total else 0.0

    # plan_match：plan.json（planning 产物）缺失 → None（N/A 不计分母，矩阵 #4）
    plan_file = run_dir / "artifacts" / "plan.json"
    plan_match: float | None = None
    if plan_file.exists():
        plan = json.loads(plan_file.read_text(encoding="utf-8"))
        actual = {n.get("agent") or n.get("program")
                  for n in plan.get("nodes", [])}
        expected = set(golden_entry.get("expect_nodes", []))
        union = actual | expected
        plan_match = len(actual & expected) / len(union) if union else 1.0

    # test_cover：executor 真执行过脚本（矩阵 #5：缺执行证据 = 0 分且计分母）。
    # 存在性语义：checkpoint 的 execute 节点 output_data 含 exit_code 即算——
    # sandbox/test_cases.py 是瞬态（沙箱回收即毁），exit_code 数值不改分只进 report
    if not golden_entry.get("expect_test", True):
        test_cover = None  # 该 defect 不期望测试 → N/A
        exec_exit: int | None = None
    else:
        exec_exit = _executor_exit_code(run_dir)
        test_cover = 1.0 if exec_exit is not None else 0.0

    # e2e_done：最后一个 run_end 事件状态（无 run_end = False，矩阵 #4 后半句）
    ends = [e for e in load_trace(run_dir) if e.get("event") == "run_end"]
    e2e_done = bool(ends) and ends[-1].get("payload", {}).get("status") == "ok"
    return {"cr_hit": cr_hit, "verdict_ok": bool(r["verdict_ok"]),
            "plan_match": plan_match, "test_cover": test_cover,
            "e2e_done": e2e_done, "exec_exit_code": exec_exit, "notes": notes}


def aggregate_task_completion(per: dict[str, dict]) -> dict:
    """跨 defect 聚合：None（N/A）跳过分子分母；全 None → None。"""
    def _mean(key: str) -> float | None:
        vals = [r[key] for r in per.values() if r.get(key) is not None]
        return sum(vals) / len(vals) if vals else None

    return {key: _mean(key) for key in
            ("cr_hit", "verdict_ok", "plan_match", "test_cover", "e2e_done")}
