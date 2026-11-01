"""真实 LLM 的做实链路冒烟（矩阵 #10 ⛳）。

context_note 描述需求 → planning 真实选链（期望激活链节点）→ 执行到
report → 断言 execution_report.md 产出且正文引用上游结论。判定走 exit code，
由 make smoke-agents 调用（该目标自动起全链 agent server，跑完 down）。
"""
from __future__ import annotations

import asyncio
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # 让 harness 包可从项目根 import

from harness.config import runs_root  # noqa: E402
from harness.engine import HarnessEngine  # noqa: E402


async def main() -> None:
    trace = "smoke-agents"
    shutil.rmtree(runs_root() / trace, ignore_errors=True)  # 清残留 checkpoint
    engine = HarnessEngine(None, runs_root())
    payload = {
        "repo": str(ROOT / "fixtures" / "demo_repo"),
        "commit": "defect-1",
        "context_note": "完整评估这次改动：先明确需求与验收标准，再定审查"
                        "策略，审查后生成测试并执行，最后汇总一份人读报告。",
    }
    await engine.execute_for(trace, payload)
    md = runs_root() / trace / "artifacts" / "execution_report.md"
    if not md.exists():
        print(f"冒烟结论: FAIL（{md} 不存在——planning 未选到含 report 的链）")
        sys.exit(1)
    text = md.read_text(encoding="utf-8")
    refs = [k for k in ("requirement", "strategy", "cr", "测试", "执行")
            if k in text]
    print(f"报告 {len(text)} 字，引用要素: {refs}")
    if len(text) < 200 or len(refs) < 2:
        print("冒烟结论: FAIL（报告过短或未引用上游结论）")
        sys.exit(1)
    print("冒烟结论: PASS（全链执行到 report，产物可读）")


if __name__ == "__main__":
    asyncio.run(main())
