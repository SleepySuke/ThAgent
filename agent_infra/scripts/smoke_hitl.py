"""真实 LLM 的 HITL 冒烟：defect-5 + 无 conventions 召回 → cr 应问人 → 答 0.20 → 命中。

前置：make dev（3 个 agent server）。用法：uv run python scripts/smoke_hitl.py
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # 让 harness 包可从项目根 import

from harness.config import runs_root  # noqa: E402
from harness.engine import DEFAULT_PLAN, HarnessEngine  # noqa: E402
from harness.memory import NoopMemory  # noqa: E402

TRACE_ID = "smoke-hitl"


def _clean_stale_run() -> None:
    # trace.jsonl 是追加写：残留上一轮的 request_human tool_call 会被本轮抢答
    #（404 自愈但要空转一轮），清掉旧 run 目录最干净
    shutil.rmtree(runs_root() / TRACE_ID, ignore_errors=True)


async def main() -> None:
    _clean_stale_run()
    engine = HarnessEngine(None, runs_root(), memory=NoopMemory())  # 关召回
    task = asyncio.create_task(engine.execute_for(
        TRACE_ID,
        {"repo": str(ROOT / "fixtures" / "demo_repo"), "commit": "defect-5",
         "context_id": "repo:demo_repo"}, DEFAULT_PLAN))
    # 轮询 trace 等 request_human 的 tool_call，出现即作答（可重复问，逐个答）
    answered = 0
    while not task.done():
        await asyncio.sleep(2)
        f = runs_root() / TRACE_ID / "trace.jsonl"
        if not f.exists():
            continue
        tr = [json.loads(line) for line in f.read_text(encoding="utf-8").splitlines()]
        hitl = [e for e in tr if e["event"] == "tool_call"
                and e["payload"].get("tool") == "request_human"]
        if len(hitl) > answered:
            answered = len(hitl)
            # args 是回调层的 repr 短串（_short），非 dict——原样展示
            print(f"cr 提问: {hitl[-1]['payload'].get('args', '')}", flush=True)
            async with httpx.AsyncClient(trust_env=False, timeout=10.0) as cli:
                for port in (8101, 8102, 8103):
                    r = await cli.post(
                        f"http://127.0.0.1:{port}/internal/hitl/{TRACE_ID}",
                        json={"text": "本仓库折扣率上限 20%（rate <= 0.20）"})
                    if r.status_code == 200:
                        print("已作答 → 等待 run 完成", flush=True)
                        break
                else:
                    print("作答失败：无 server 接受（agent 未在等待？）", flush=True)
    await asyncio.wait_for(task, timeout=600)
    rep = runs_root() / TRACE_ID / "artifacts" / "cr_report.json"
    report = json.loads(rep.read_text(encoding="utf-8"))
    hit = any("promo" in (i.get("file", "")) for i in report["issues"])
    # 问人是模型自主决策（prompt 仅在关键信息缺失时要求问）：docstring 与代码
    # 一致后，promo 只能靠召回的约定（上限 0.20）命中——问人次数确认 HITL 路径
    print(f"verdict={report['verdict']} 问人次数={answered} defect-5 命中={hit}")
    print("冒烟结论:", "PASS" if hit else "FAIL（未通过 convention-only 命中）")


if __name__ == "__main__":
    asyncio.run(main())
