"""九期审阅回路真实冒烟（controller 执行，烧 LLM）：reject → replan → accept。

不设 AGENT_INFRA_REVIEW_AUTO——真实走 park 等人裁决。流程：defect-2 全链跑完
park 在 REVIEW_PENDING → engine.review_run(reject, feedback) → 等 round=2 新
报告再审 → accept → 断言 distilled 落盘 + checkpoint completed。每步打印证据，
判定走 exit code（make smoke-review 调用，服务器由该目标自起）。
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from harness.config import runs_root  # noqa: E402
from harness.engine import HarnessEngine  # noqa: E402

TRACE = "smoke-review"
FEEDBACK = "补充边界测试：新增档位与既有用例的契约冲突场景"
REVIEW_WAIT_S = 600      # 全链执行 + park 的等待上限（真实 LLM 慢）
REPLAN_WAIT_S = 900      # replan 二轮执行更长


def _fail(reason: str) -> None:
    print(f"冒烟结论: FAIL（{reason}）")
    sys.exit(1)


def _cp(trace: str) -> dict:
    f = runs_root() / trace / "checkpoint.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


async def _wait_review(engine: HarnessEngine, timeout: float) -> None:
    """轮询等 review_pending（review_event 已建未 set；用 docstring 语义）。"""
    async def ready():
        h = engine._runs.get(TRACE)
        return (h is not None and h.review_event is not None
                and not h.review_event.is_set())
    deadline = asyncio.get_running_loop().time() + timeout
    while not await ready():
        if asyncio.get_running_loop().time() > deadline:
            _fail(f"{REVIEW_WAIT_S}s 内未进入 review_pending")
        await asyncio.sleep(1.0)


async def main() -> None:
    shutil.rmtree(runs_root() / TRACE, ignore_errors=True)   # 清残留 checkpoint
    engine = HarnessEngine(None, runs_root())
    payload = {
        "repo": str(ROOT / "fixtures" / "demo_repo"),
        "commit": "defect-2",   # pricing 档位：语料有沉淀，召回应真实命中
        "context_note": "完整评估这次改动：需求与验收 → 审查策略 → 代码审查 → "
                        "检索既有用例出变更分析报告 → 用例设计 → 脚本生成执行 → "
                        "失败根因分析 → 执行报告",
    }
    task = asyncio.create_task(engine.execute_for(TRACE, payload))

    # ① 一轮执行 → park
    t0 = time.time()
    await _wait_review(engine, REVIEW_WAIT_S)
    cp = _cp(TRACE)
    print(f"[1] park 于 review_pending（round={cp.get('round')}，"
          f"耗时 {time.time() - t0:.0f}s）")
    if cp.get("round") != 1:
        _fail(f"一轮 checkpoint round 应为 1，实为 {cp.get('round')}")
    report_md = runs_root() / TRACE / "artifacts" / "execution_report.md"
    if not report_md.exists():
        _fail("park 时 execution_report.md 不存在——报告未产出即 park")
    print(f"[2] 一轮执行报告 {len(report_md.read_text(encoding='utf-8'))} 字")

    # ② reject → replan → 二轮再 park
    t0 = time.time()
    if not engine.review_run(TRACE, "reject", FEEDBACK):
        _fail("review_run(reject) 被拒——run 不在等裁决态")
    print(f"[3] 已提交 reject（feedback={FEEDBACK!r}），等 replan 二轮…")
    await _wait_review(engine, REPLAN_WAIT_S)
    cp = _cp(TRACE)
    print(f"[4] 二轮 park（round={cp.get('round')}，耗时 {time.time() - t0:.0f}s）")
    if cp.get("round") != 2:
        _fail(f"二轮 checkpoint round 应为 2，实为 {cp.get('round')}")
    trace = [json.loads(line) for line in
             (runs_root() / TRACE / "trace.jsonl").read_text().splitlines()]
    if not any(e["event"] == "review_rejected" for e in trace):
        _fail("trace 无 review_rejected 事件")

    # ③ accept → COMPLETED + 蒸馏
    if not engine.review_run(TRACE, "accept"):
        _fail("review_run(accept) 被拒")
    await task
    cp = _cp(TRACE)
    if cp.get("harness_state") != "completed":
        _fail(f"accept 后 harness_state={cp.get('harness_state')!r}，应 completed")
    print("[5] accept → checkpoint completed")
    distilled = [p for p in (ROOT / "knowledge" / "distilled").glob("*.md")
                 if f"source_run_id: {TRACE}" in p.read_text(encoding="utf-8")]
    if not distilled:
        _fail("knowledge/distilled 无本 run 的蒸馏条目——飞轮未落盘")
    print(f"[6] 蒸馏条目 {len(distilled)} 个："
          f"{'、'.join(p.name for p in distilled)}")
    print("冒烟结论: PASS（reject→replan(round2)→accept 全回路，蒸馏落盘）")


if __name__ == "__main__":
    asyncio.run(main())
