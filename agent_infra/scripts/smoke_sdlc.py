"""真实 LLM 的八期全链冒烟（矩阵 #14 ⛳，controller 执行）。

context_note 描述完整评估 → planning 真实选 9 节点全链（可能含 diagnose）→
双报告与召回断言：①change_report.md 含召回/复用与建议；②execution_report.md
含通过率；③test_recall.json 的 recalled 非空且每条 case_id TC- 前缀、source
非空（reuse 可溯源）；④两报告各 ≥200 字。判定走 exit code，由 make
smoke-sdlc 调用（该目标自动起 agent server，跑完 down）。
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # 让 harness 包可从项目根 import

from harness.config import runs_root  # noqa: E402
from harness.engine import HarnessEngine  # noqa: E402


def _fail(reason: str) -> None:
    print(f"冒烟结论: FAIL（{reason}）")
    sys.exit(1)


async def main() -> None:
    trace = "smoke-sdlc"
    shutil.rmtree(runs_root() / trace, ignore_errors=True)  # 清残留 checkpoint
    engine = HarnessEngine(None, runs_root())
    payload = {
        "repo": str(ROOT / "fixtures" / "demo_repo"),
        # defect-2（pricing 档位）：语料 TC-001/002/003 正是 pricing 用例——
        # 召回应真实命中（defect-1 的风险在 stats.py，语料无沉淀，召回空是
        # 诚实降级不是链路缺陷——首轮实测 recalled=[] 即此因）
        "commit": "defect-2",
        "context_note": "完整评估这次改动：需求与验收 → 审查策略 → 代码审查 → "
                        "检索既有用例出变更分析报告 → 用例设计 → 脚本生成执行 → "
                        "失败根因分析 → 执行报告",
    }
    await engine.execute_for(trace, payload)
    arts = runs_root() / trace / "artifacts"

    # ③ 召回可溯源：recalled 非空，每条 case_id 以 TC- 开头、source 非空
    recall_file = arts / "test_recall.json"
    if not recall_file.exists():
        _fail(f"{recall_file} 不存在——planning 未选到含 test_recall 的链")
    recalled = json.loads(recall_file.read_text(encoding="utf-8")).get("recalled", [])
    if not recalled:
        _fail("recalled 为空——语料检索未命中")
    for it in recalled:
        if not str(it.get("case_id", "")).startswith("TC-"):
            _fail(f"recalled 条目 case_id 非 TC- 前缀: {it.get('case_id')!r}")
        if not it.get("source"):
            _fail(f"recalled 条目 source 为空: {it.get('case_id')!r}")

    # ①④ 变更分析报告：含（复用|召回）与建议，且 ≥200 字
    change_md = arts / "change_report.md"
    if not change_md.exists():
        _fail(f"{change_md} 不存在——planning 未选到含 change_report 的链")
    change_text = change_md.read_text(encoding="utf-8")
    if not (("复用" in change_text or "召回" in change_text)
            and "建议" in change_text):
        _fail("change_report.md 缺召回/复用与建议要素")
    if len(change_text) < 200:
        _fail(f"change_report.md 过短（{len(change_text)} 字）")

    # ②④ 执行报告：含通过率（pass_rate 或「通过率」），且 ≥200 字
    exec_md = arts / "execution_report.md"
    if not exec_md.exists():
        _fail(f"{exec_md} 不存在——planning 未选到含 report 的链")
    exec_text = exec_md.read_text(encoding="utf-8")
    if "pass_rate" not in exec_text and "通过率" not in exec_text:
        _fail("execution_report.md 缺通过率")
    if len(exec_text) < 200:
        _fail(f"execution_report.md 过短（{len(exec_text)} 字）")

    print(f"召回 {len(recalled)} 条；变更报告 {len(change_text)} 字；"
          f"执行报告 {len(exec_text)} 字")
    print("冒烟结论: PASS（全链双报告产出，召回条目可溯源）")


if __name__ == "__main__":
    asyncio.run(main())
