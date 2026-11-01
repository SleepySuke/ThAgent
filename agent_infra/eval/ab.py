"""A/B 评测：memory 开（Hybrid）vs 关（Noop）各跑一遍缺陷集，比 CR 命中率。

注意：自 RAG 阶段起 B 组默认带 knowledge 推通道腿（build_memory 默认挂载
KnowledgeBase），是 Hybrid+knowledge 对照而非纯 memory 对照。

前置：3 个 agent server 已起（make dev）。用法：uv run python eval/ab.py
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.evaluate import evaluate_report, load_golden  # noqa: E402
from harness.config import runs_root  # noqa: E402
from harness.engine import DEFAULT_PLAN, HarnessEngine  # noqa: E402
from harness.memory import build_memory  # noqa: E402

REPO = str(ROOT / "fixtures" / "demo_repo")
CONTEXT_ID = "repo:demo_repo"
CONVENTIONS = ROOT / "eval" / "conventions.json"


async def _run_suite(engine: HarnessEngine, golden: dict) -> dict:
    reports: dict[str, dict] = {}
    for tag in golden:
        trace_id = await engine.execute(
            {"repo": REPO, "commit": tag, "context_id": CONTEXT_ID}, DEFAULT_PLAN)
        report = runs_root() / trace_id / "artifacts" / "cr_report.json"
        if not report.exists():
            sys.exit(f"missing cr_report for {tag} ({trace_id}) — did you run make dev?")
        reports[tag] = json.loads(report.read_text())
    return evaluate_report(golden, reports)


async def main() -> None:
    golden = load_golden()
    runs = runs_root()

    # 每次 A/B 从干净 experiences 语料开始：跨次运行的残留沉淀会让 IDF/候选漂移、
    # 结果不可复现。B 组内部跨 run 的 record→recall（past_review 生效）不受影响。
    exp = runs / "memory" / "experiences.jsonl"
    if exp.exists():
        exp.unlink()

    engine_a = HarnessEngine(None, runs)  # Noop（基线）
    engine_b = HarnessEngine(
        None, runs,
        memory=build_memory(runs, enabled=True, conventions_path=CONVENTIONS))

    a = await _run_suite(engine_a, golden)
    b = await _run_suite(engine_b, golden)

    print("== A/B 对比 ==")
    print(f"A(Noop)    hit_rate={a['total_hit_rate']:.2f} "
          f"fp={a['total_false_positives']} verdict={a['verdict_accuracy']:.2f}")
    print(f"B(Hybrid+knowledge) hit_rate={b['total_hit_rate']:.2f} "
          f"fp={b['total_false_positives']} verdict={b['verdict_accuracy']:.2f}")
    delta = b["total_hit_rate"] - a["total_hit_rate"]
    print(f"hit_rate Δ = {delta:+.2f}")
    if delta > 0 and b["total_false_positives"] <= a["total_false_positives"]:
        print("结论: memory 是收益")
    elif delta < 0 or b["total_false_positives"] > a["total_false_positives"]:
        print("结论: memory 是污染")
    else:
        print("结论: memory 无影响")


if __name__ == "__main__":
    asyncio.run(main())
