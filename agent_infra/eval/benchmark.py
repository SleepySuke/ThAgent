"""V 层：Benchmark 编排器——在线跑/离线重放 → 三维打分 → 对比基线 → 门禁。

用法（设计 §2 控制平面）：
  在线（烧 LLM，服务器由 make eval 自起，EVAL_ENV=HITL auto）：
      uv run python eval/benchmark.py
  离线重放（零 LLM，CI 可高频）：
      uv run python eval/benchmark.py --from runs/smoke-agents   # 单 run 报告
      uv run python eval/benchmark.py --from runs                # 父目录聚合+门禁
  建基线：--update-baseline（当前指标写入 eval/baseline.json，人审后固化）

首跑建基线三步（设计 §6）：make eval（exit 0 + 建基线提示）→ 人审
runs/bench/scores.json → make eval-update 固化 → 二次 make eval 应 exit 0。

门禁（设计 §3.2/§4）：核心指标绝对降幅 >5pp 或相对降幅 >10% → exit 1 且
点名掉点指标；聚合模式覆盖不全（缺 defect）fail-closed exit 1——部分覆盖
对全量基线不可比；单 defect 打分/执行异常不拖垮整轮（记 error 行，exit 1）；
--update-baseline 遇坏 run（覆盖不全/打分异常）拒绝写基线 exit 1；
--from 指向不存在目录或文件 exit 2；baseline.json 不存在 exit 0 给建基线
指引（不挡首跑）。缺产物响亮报错绝不静默 0 分（三期教训）。
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.evaluate import load_golden  # noqa: E402
from eval.task_completion import (  # noqa: E402
    aggregate_task_completion,
    score_task_completion,
)
from eval.tool_calling import load_trace, score_tool_calling  # noqa: E402
from harness.config import runs_root  # noqa: E402

REPO = str(ROOT / "fixtures" / "demo_repo")
BASELINE_PATH = Path(__file__).parent / "baseline.json"
SCORES_PATH = runs_root() / "bench" / "scores.json"
TRACE_PREFIX = "bench-"
# 门禁核心指标（掉点报警面；denied/tool_calls/turns_per_node 只报告不门禁——
# 轮次上升不是「掉点」，双向阈值留待需要时再加）
CORE_METRICS = (
    "tool_calling.legality", "tool_calling.must_use_hit",
    "task_completion.cr_hit", "task_completion.verdict_ok",
    "task_completion.plan_match", "task_completion.test_cover",
    "task_completion.e2e_done",
    # 质量硬维度进门禁（裁定 B：软维度 judge 方差不进回归判据，只记录）
    "quality.evidence",
)
ABS_DROP = 0.05   # 绝对降幅阈值（5pp）
REL_DROP = 0.10   # 相对降幅阈值（10%)


def score_run(golden_entry: dict, run_dir: Path) -> dict:
    """单 defect 三维打分：tool_calling + task_completion + quality（离线）。"""
    events = load_trace(run_dir)
    out = {"tool_calling": score_tool_calling(
               events, golden_entry.get("must_use", {})),
           "task_completion": score_task_completion(golden_entry, run_dir)}
    # 质量分离线算（裁定 A：不依赖 engine 事件）；hard-only 默认不烧 judge，
    # 设 AGENT_INFRA_QUALITY_JUDGE 时软维度一并记录（仍不门禁，裁定 B）
    report_file = run_dir / "artifacts" / "cr_report.json"
    if report_file.exists():
        from eval.quality import score_report
        try:
            report = json.loads(report_file.read_text(encoding="utf-8"))
            complete = _llm_judge if os.environ.get(
                "AGENT_INFRA_QUALITY_JUDGE") else None
            out["quality"] = score_report(
                report, REPO, _commit_of(run_dir) or "", complete=complete)
        except Exception as e:  # 打分异常不拖垮既有三维（矩阵 #8 同款隔离）
            out["quality_error"] = f"{type(e).__name__}: {e}"
    return out


def _llm_judge(prompt: str) -> str:
    """软维度 judge 通道（litellm）；仅 AGENT_INFRA_QUALITY_JUDGE 时走。"""
    from eval.quality import _llm_complete
    return _llm_complete(prompt)


def score_defects(golden: dict, run_dirs: dict[str, Path]) -> tuple[dict, bool]:
    """逐 defect 打分；单 defect 异常记 error 行不拖垮整轮（矩阵 #8/#9）。"""
    rows: dict = {}
    had_error = False
    for tag, entry in golden.items():
        run_dir = run_dirs.get(tag)
        if run_dir is None:
            rows[tag] = {"error": "no run for defect"}  # 响亮，不静默 0 分
            had_error = True
            continue
        try:
            rows[tag] = score_run(entry, run_dir)
        except Exception as e:  # 打分自身异常隔离（🔥 矩阵 #8）
            rows[tag] = {"error": f"{type(e).__name__}: {e}"}
            had_error = True
    return rows, had_error


async def run_online(golden: dict, engine=None) -> dict[str, Path]:
    """在线模式：engine 跑全部 defect（planning 真实选链，Noop memory）。

    单 defect 执行异常不拖垮整轮（矩阵 #9）：异常 run 的目录保留供打分
    （多为低分/目录缺失进 error 行）；engine 参数是测试注入口。
    """
    if engine is None:
        from harness.engine import HarnessEngine
        engine = HarnessEngine(None, runs_root())
    out: dict[str, Path] = {}
    for tag in golden:
        # ponytail: trace 带轮次 uniquifier——ADK session 按 trace:node 全局
        # 持久（adk_sessions.db），固定 trace_id 重跑会让模型看到旧轮对话
        # （坑 #25 姊妹坑，实测模型把重复输入当续聊回叙事文本→parse_plan 拒）。
        # 前缀保 bench- 供 _pick_run 识别；rmtree 仍清旧目录（打分读最新）
        n = 1
        while (runs_root() / f"{TRACE_PREFIX}{tag}-{n}").exists():
            n += 1
        trace_id = f"{TRACE_PREFIX}{tag}-{n}"
        # 矩阵 #9：失败不中断其余 defect，完成度如实由打分体现
        with contextlib.suppress(Exception):
            await engine.execute_for(trace_id, {"repo": REPO, "commit": tag})
        out[tag] = runs_root() / trace_id
    return out


def _commit_of(run_dir: Path) -> str | None:
    for e in load_trace(run_dir):
        if e.get("event") == "run_start":
            # 引擎 emit("run_start", payload=…) 会把整个 run payload 嵌进
            # record.payload.payload（真实 trace 形状）；合成 fixture 是平铺
            p = e.get("payload", {})
            return p.get("commit") or p.get("payload", {}).get("commit")
    return None


def _pick_run(cands: list[Path]) -> Path:
    """同 commit 多 run 选择：bench- 前缀目录优先（在线门禁 run 是权威产出），
    其余按 trace.jsonl mtime 最新——陈旧的非门禁 run 不得顶替新门禁 run。"""
    pool = [c for c in cands if c.name.startswith(TRACE_PREFIX)] or cands
    return max(pool, key=lambda c: (c / "trace.jsonl").stat().st_mtime)


def collect_offline(from_dir: Path) -> tuple[dict[str, Path], bool]:
    """离线收集：单 run 目录直取（报告模式）；父目录扫描按 commit 归组。

    返回 (run_dirs, single)；single=True 不进门禁（单 defect 指标对 5-defect
    基线不可比）。目录不存在/指向文件/无有效 run → SystemExit(2)（矩阵 #6，
    响亮）。
    """
    from_dir = Path(from_dir)
    if not from_dir.exists():
        print(f"--from 目录不存在: {from_dir}")
        raise SystemExit(2)
    if from_dir.is_file():
        print(f"--from 指向的是文件不是目录: {from_dir}")
        raise SystemExit(2)
    if (from_dir / "trace.jsonl").exists():
        tag = _commit_of(from_dir)
        if not tag:
            print(f"run 缺 run_start.commit，无法定位 golden: {from_dir}")
            raise SystemExit(2)
        return {tag: from_dir}, True
    by_tag: dict[str, list[Path]] = {}
    for d in sorted(from_dir.iterdir()):
        if not (d / "trace.jsonl").exists():
            continue
        tag = _commit_of(d)
        if not tag:
            print(f"跳过无 commit 的 run: {d.name}")
            continue
        by_tag.setdefault(tag, []).append(d)
    runs: dict[str, Path] = {}
    for tag, cands in by_tag.items():  # 每 tag 打印选中的 run（审计线索）
        chosen = _pick_run(cands)
        extra = f"（{len(cands)} 个候选）" if len(cands) > 1 else ""
        print(f"{tag}: 选中 run {chosen.name}{extra}")
        runs[tag] = chosen
    if not runs:
        print(f"--from 下没有有效 run 目录: {from_dir}")
        raise SystemExit(2)
    return runs, False


def aggregate_metrics(rows: dict) -> dict:
    """各 defect 行 → 基线可比的聚合指标（scores.json/baseline.json 的 metrics）。

    n_defects：本轮成功打分的 defect 数（进基线——门禁对比时口径可见）；
    per_defect：每 defect 的核心指标（漂移定位到单个 defect 用，人不猜）。
    """
    ok = {t: r for t, r in rows.items() if "error" not in r}
    n = len(ok) or 1
    sums: dict[str, float] = {}
    turns: dict[str, list[int]] = {}
    denied = calls = 0
    for r in ok.values():
        t = r["tool_calling"]
        for k in ("legality", "must_use_hit"):
            sums[k] = sums.get(k, 0.0) + t[k]
        denied += t["denied"]
        calls += t["tool_calls"]
        for agent, turn in t["turns_per_node"].items():
            turns.setdefault(agent, []).append(turn)
    tk = aggregate_task_completion(
        {t: r["task_completion"] for t, r in ok.items()}) if ok else {
            k: None for k in ("cr_hit", "verdict_ok", "plan_match",
                              "test_cover", "e2e_done")}
    per_defect = {}
    evs: list[float] = []
    for t, r in ok.items():
        tc, tk_row = r["tool_calling"], r["task_completion"]
        q = r.get("quality") or {}
        ev = q.get("evidence")
        if ev is not None:
            evs.append(ev)
        per_defect[t] = {"legality": tc["legality"],
                         "must_use_hit": tc["must_use_hit"],
                         **{k: tk_row[k] for k in ("cr_hit", "verdict_ok",
                                                   "plan_match", "test_cover",
                                                   "e2e_done")},
                         "quality_evidence": ev}
    return {"n_defects": len(ok), "per_defect": per_defect,
            "quality": {"evidence":
                        round(sum(evs) / len(evs), 4) if evs else None},
            "tool_calling": {
                "legality": round(sums.get("legality", 0.0) / n, 4),
                "must_use_hit": round(sums.get("must_use_hit", 0.0) / n, 4),
                "denied": denied, "tool_calls": calls,
                "turns_per_node": {a: round(sum(v) / len(v), 1)
                                   for a, v in sorted(turns.items())}},
            "task_completion": tk}


def _get(metrics: dict, dotted: str):
    group, key = dotted.split(".")
    return metrics.get(group, {}).get(key)


def diff_baseline(metrics: dict, baseline: dict) -> list[dict]:
    """核心指标漂移行：绝对降幅 >5pp 或相对 >10% 即 fail（设计 §4）。

    量子声明：cr_hit/verdict_ok 等 0-1 指标是按 defect 数平均的聚合，当前
    5-defect 集上最小步长（量子）= 0.2——任何下降都至少是 1 个 defect 翻转，
    等效零翻转容忍。多副本均值平滑是升级路径（quota 受限暂缓）。
    """
    rows = []
    for key in CORE_METRICS:
        b, c = _get(baseline, key), _get(metrics, key)
        if b is None or c is None:
            continue  # N/A（如 plan_match 全缺失/基线未含）不进门禁
        drop = b - c
        rows.append({"metric": key, "base": b, "cur": c, "drop": round(drop, 4),
                     "fail": drop > ABS_DROP or drop > REL_DROP * b})
    return rows


def load_baseline() -> dict | None:
    if not BASELINE_PATH.exists():
        return None
    return json.loads(BASELINE_PATH.read_text(encoding="utf-8"))


def write_baseline(metrics: dict, source: str) -> None:
    """写基线（矩阵 #14：含生成时间与源 run；人审后由用户提交入库）。

    tmp + os.replace 原子写：中断不留半文件（半文件下次 load 即 JSON 崩）。
    """
    tmp = BASELINE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(
        {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
         "source": source, "metrics": metrics},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, BASELINE_PATH)


def _print_report(rows: dict, metrics: dict, scores_path: Path) -> None:
    """逐 defect 报告（error 行显式标注）+ 汇总行。"""
    for tag, row in rows.items():
        if "error" in row:
            print(f"{tag}: ERROR {row['error']}")
            continue
        tc, tk = row["tool_calling"], row["task_completion"]
        q = row.get("quality") or {}
        ev = q.get("evidence")
        print(f"{tag}: legality={tc['legality']:.2f} denied={tc['denied']} "
              f"must_use={tc['must_use_hit']:.2f} | cr_hit={tc_hit(tk)} "
              f"plan={tk['plan_match']} cover={tk['test_cover']} "
              f"e2e={tk['e2e_done']} | "
              f"evidence={ev if ev is not None else 'N/A'}")
    m = metrics
    print(f"\n汇总: legality={m['tool_calling']['legality']:.2f} "
          f"must_use={m['tool_calling']['must_use_hit']:.2f} "
          f"cr_hit={m['task_completion']['cr_hit']} "
          f"e2e={m['task_completion']['e2e_done']} -> {scores_path}")


def _gate(metrics: dict, drift: list, single: bool, missing: list,
          had_error: bool, *, gated: bool) -> None:
    """门禁判定与退出（设计 §3.2/§4 + C1 覆盖 fail-closed + I4 量子声明）。"""
    fails = [d for d in drift if d["fail"]]
    if fails:  # 矩阵 #13：点名掉点指标
        print("基准漂移（掉点超阈）:")
        for d in fails:
            print(f"  {d['metric']}: {d['base']} -> {d['cur']} (drop {d['drop']})")
        n = metrics.get("n_defects")
        if n:  # I4 量子声明：0-1 聚合的最小步长，读数人不当连续值解读
            print(f"  注: 0-1 聚合指标在当前 {n}-defect 集上量子={1 / n:.2g}"
                  "（等效零翻转容忍）")
    if had_error:
        print("存在打分异常 defect（见上 ERROR 行）")
    if missing and not single:
        print(f"覆盖不全，缺失 defect: {missing}（部分覆盖对基线不可比）")
    if fails or had_error or (missing and not single):
        raise SystemExit(1)
    print("Benchmark 门禁通过" if gated else (
        "单 run 报告模式（不进门禁）" if single else "首跑完成（未建基线）"))


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description="Benchmark：三维打分 + 漂移门禁")
    ap.add_argument("--from", dest="from_dir", type=Path, default=None,
                    help="离线重放的 run 目录（单 run 或父目录）")
    ap.add_argument("--update-baseline", action="store_true",
                    help="当前指标写入 eval/baseline.json（人审后固化）")
    ap.add_argument("--source", default=None,
                    help="基线 source 标注（默认 online:bench / offline:<目录名>，"
                         "不记机器本地绝对路径）")
    args = ap.parse_args(argv)

    golden = load_golden()
    if args.from_dir is not None:
        run_dirs, single = collect_offline(args.from_dir)
        source = args.source or f"offline:{args.from_dir.name}"
    else:
        run_dirs = asyncio.run(run_online(golden))
        single = False
        source = args.source or "online:bench"
    rows, had_error = score_defects(
        {t: golden[t] for t in run_dirs if t in golden}, run_dirs)
    unknown = sorted(t for t in run_dirs if t not in golden)
    if unknown:
        print(f"忽略不在 golden 里的 run: {unknown}")
    metrics = aggregate_metrics(rows)
    # C1 覆盖完整性：聚合模式缺 defect = 部分覆盖，对 5-defect 基线不可比，
    # fail-closed（绝不静默按子集聚合放行）
    missing = sorted(set(golden) - set(rows))

    baseline = None if single else load_baseline()
    if (baseline is None and not single and not args.update_baseline):
        print("eval/baseline.json 不存在——首跑建基线：人审 runs/bench/scores.json"
              " 后执行 make eval-update（--update-baseline）固化")  # 矩阵 #7
    gated = not single and not args.update_baseline and baseline is not None
    drift = diff_baseline(metrics, baseline["metrics"]) if gated else []

    # M2：单 run 报告模式的分数落在 <run_dir>/scores.json——runs/bench/scores.json
    # 是门禁 run 的记录，被覆写会让人审看错对象
    scores_path = (next(iter(run_dirs.values())) / "scores.json" if single
                   else SCORES_PATH)
    scores_path.parent.mkdir(parents=True, exist_ok=True)
    scores_path.write_text(json.dumps(
        {"mode": "offline" if args.from_dir else "online",
         "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
         "defects": rows, "metrics": metrics,
         "baseline": {"exists": baseline is not None, "gated": gated,
                      "drift": drift}},
        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    _print_report(rows, metrics, scores_path)

    if args.update_baseline:
        # I1：坏 run 不得写根信任——覆盖不全（含单 run 模式）或有打分异常一律
        # 拒绝，人审是 backstop 不是替代
        if single or missing or had_error:
            why = ["单 run 报告模式"] if single else []
            why += [f"缺失 defect {missing}"] if missing else []
            why += ["存在打分异常 defect"] if had_error else []
            print("拒绝写基线（" + "；".join(why) + "）——人审是 backstop 不是替代")
            raise SystemExit(1)
        write_baseline(metrics, source)  # 矩阵 #14
        print(f"基线已写入 {BASELINE_PATH}（source={source}）——二次运行走门禁")
        return
    _gate(metrics, drift, single, missing, had_error, gated=gated)


def tc_hit(tk: dict) -> str:
    """cr_hit 的报告格式（None 安全，四位小数浮点）。"""
    return f"{tk['cr_hit']:.2f}" if tk["cr_hit"] is not None else "N/A"


if __name__ == "__main__":
    main()
