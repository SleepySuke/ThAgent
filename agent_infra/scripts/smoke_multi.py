"""多 agent 闭环冒烟：直接调 engine 跑完整链路（planning → cr → testing → execute）。

前置：3 个 agent server 已起（`make dev`，或分别 `make server-cr/testing/planning`）。
用法：`uv run python scripts/smoke_multi.py [commit]`（默认 defect-1）。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # 让 harness 包可从项目根 import

from harness.config import runs_root  # noqa: E402
from harness.engine import HarnessEngine  # noqa: E402

REPO = str(ROOT / "fixtures" / "demo_repo")


async def main() -> None:
    commit = sys.argv[1] if len(sys.argv) > 1 else "defect-1"
    runs = runs_root()
    engine = HarnessEngine(None, runs)
    print(f"submitting commit={commit} ...", flush=True)
    trace_id = await engine.execute({"repo": REPO, "commit": commit})
    print(f"trace_id={trace_id}\n", flush=True)

    trace = [json.loads(line) for line in
             (runs / trace_id / "trace.jsonl").read_text(encoding="utf-8").splitlines()]
    print("== state transitions ==")
    for e in trace:
        if e["event"] == "state_transition":
            p = e["payload"]
            print(f"  {p['from_']} --{p['trigger']}--> {p['to']}")
    print("\n== node results ==")
    for e in trace:
        if e["event"] == "node_end":
            print(f"  [{e['node_id']}] status={e['payload']['status']}")
    print("\n== artifacts ==")
    artifacts = runs / trace_id / "artifacts"
    if artifacts.exists():
        for f in sorted(artifacts.iterdir()):
            print(f"  --- {f.name} ---")
            print("  " + f.read_text(encoding="utf-8")[:1500].replace("\n", "\n  "))


if __name__ == "__main__":
    asyncio.run(main())
