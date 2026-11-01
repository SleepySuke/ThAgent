"""真实 LLM 的 RAG 冒烟（矩阵 #16）：defect-5 × 知识层开/关对照。

两侧都用空 conventions（隔离三期种子）：关=无 knowledge 腿（agent 仍可自由调
search_knowledge 拉通道），开=推+拉双通道。开侧命中 promo 且关侧漏报为 PASS；
关侧也命中说明模型主动检索自救（拉通道收益，推通道增量无法隔离，打印提示）。
门禁自盲防护：臂内 search_knowledge 出现「检索失败」→ 该臂 degraded，整体
结论视为 FAIL（否则检索通道坏了会被误读成「知识层无收益」）。无头作答：轮询
trace 发现 request_human 即答「无补充信息」（绝不答 0.20——保持 OFF 臂纯度）。
前置：make dev（3 个 agent server）。用法：uv run python scripts/smoke_rag.py
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
from harness.knowledge import KnowledgeBase  # noqa: E402
from harness.memory import HybridMemory  # noqa: E402

ARM_TIMEOUT_S = 900  # 单臂看门狗：LLM 死循环/卡等待时 FAIL 而非挂死
NOOP_ANSWER = "无补充信息，请基于当前审查继续"  # 确认语义，不注入折扣信息

# defect-5 命中谓词：promo 文件 + severity 达 low/minor 及以上 + 语义关键词。
# 只按文件名匹配会把 promo 上的无关 issue 也算命中。语义双闸：
# ① severity ≥ mid——死代码角度实测是 low（终审取证），知识驱动的命中是 mid；
# ② 关键词必须是「违规语义」而非话题词——任何 promo issue 的 desc 都会谈到折扣，
#    所以裸「折扣/discount」不设闸，用 上限/0.2/超/审批/绕过/唯一折扣来源。
_SEV_FLOOR = {"critical", "blocker", "high", "mid", "medium"}
_KEYWORDS = ("上限", "0.2", "超", "审批", "绕过", "唯一折扣来源")


def _empty_conventions() -> Path:
    p = runs_root() / "smoke-rag-empty-conventions.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("[]", encoding="utf-8")
    return p


def _read_trace(trace_id: str) -> list[dict]:
    f = runs_root() / trace_id / "trace.jsonl"
    if not f.exists():
        return []
    out = []
    for line in f.read_text(encoding="utf-8").splitlines():
        try:  # 进程中途被杀的半行跳过
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _hit_defect5(issues: list[dict]) -> bool:
    """severity 宽容大小写；desc/issue 全文任一关键词命中即可。"""
    for i in issues:
        text = json.dumps(i, ensure_ascii=False).lower()
        if ("promo" in str(i.get("file", "")).lower()
                and str(i.get("severity", "")).lower() in _SEV_FLOOR
                and any(k in text for k in _KEYWORDS)):
            return True
    return False


def _search_failures(events: list[dict]) -> list[str]:
    """臂内 search_knowledge 的 tool_result 含「检索失败」→ 检索通道异常。"""
    return [str(e["payload"].get("result", ""))
            for e in events
            if e.get("event") == "tool_result"
            and e.get("payload", {}).get("tool") == "search_knowledge"
            and "检索失败" in str(e["payload"].get("result", ""))]


async def _answer_noop(bases: list[str], trace_id: str) -> None:
    """广播 /internal/hitl（app 的 /runs/{tid}/hitl 同款转发目标）。"""
    async with httpx.AsyncClient(trust_env=False, timeout=10.0) as cli:
        for base in bases:
            try:
                r = await cli.post(f"{base}/internal/hitl/{trace_id}",
                                   json={"text": NOOP_ANSWER})
            except httpx.HTTPError:
                continue  # server 不在/未起：试下一个
            if r.status_code == 200:
                print("已作答（无补充信息）→ 等待 run 继续", flush=True)
                return
        print("作答失败：无 server 接受（agent 未在等待？）", flush=True)


async def _run(arm: str, memory) -> tuple[bool, bool]:
    """跑单臂，返回 (defect-5 命中, 检索通道 degraded)。"""
    trace = f"smoke-rag-{arm}"
    shutil.rmtree(runs_root() / trace, ignore_errors=True)  # 清残留 checkpoint
    engine = HarnessEngine(None, runs_root(), memory=memory)
    task = asyncio.create_task(engine.execute_for(
        trace, {"repo": str(ROOT / "fixtures" / "demo_repo"),
                "commit": "defect-5", "context_id": "repo:demo_repo"},
        DEFAULT_PLAN))
    # 无头答题（移植 smoke_hitl 的轮询模式）：2s 轮询 request_human，逐个答
    answered = 0
    while not task.done():
        await asyncio.sleep(2)
        hitl = [e for e in _read_trace(trace) if e["event"] == "tool_call"
                and e["payload"].get("tool") == "request_human"]
        if len(hitl) > answered:
            answered = len(hitl)
            print(f"[{arm}] cr 提问: {hitl[-1]['payload'].get('args', '')}",
                  flush=True)
            await _answer_noop(engine.node_urls(), trace)
    try:
        await task
    except Exception as e:
        print(f"FAIL: {arm} run 异常: {e}（见 runs/{trace}/trace.jsonl）")
        sys.exit(1)
    rep = runs_root() / trace / "artifacts" / "cr_report.json"
    if not rep.exists():
        print(f"FAIL: {arm} run 未产出 cr_report（见 runs/{trace}/trace.jsonl）")
        sys.exit(1)
    errs = _search_failures(_read_trace(trace))
    if errs:
        print(f"WARN [{arm}] 检索通道异常: {errs[0]}")
    report = json.loads(rep.read_text(encoding="utf-8"))
    return _hit_defect5(report.get("issues", [])), bool(errs)


async def main() -> None:
    conv = _empty_conventions()
    runs = runs_root()
    # 适配（超出 brief 的空 conventions 隔离）：memory 腿指向每臂独立目录——
    # 真实 runs/memory 里残留的 past_review（defect-2/4/5 均引用 0.20 上限）
    # 会让 OFF 臂命中、OFF 臂 record 又会串进 ON 臂，对照失效；隔离后增量即
    # 知识层。knowledge 索引仍用真实 runs/knowledge（make knowledge-index 产物）
    mem = runs / "smoke-rag-mem"
    shutil.rmtree(mem, ignore_errors=True)  # 上轮冒烟自身的 past_review 同样要隔离
    # 看门狗包整臂（run + 答题轮询）：超时即 FAIL，绝不无限挂死
    off = await asyncio.wait_for(
        _run("off", HybridMemory(mem / "off", conv)), ARM_TIMEOUT_S)
    on = await asyncio.wait_for(
        _run("on", HybridMemory(
            mem / "on", conv, knowledge=KnowledgeBase(runs))), ARM_TIMEOUT_S)
    degraded = off[1] or on[1]
    print(f"关（无知识注入）defect-5 命中={off[0]}")
    print(f"开（知识注入）  defect-5 命中={on[0]}")
    if on[0] and not off[0]:
        verdict = "PASS（知识层是命中增量的来源）"
    elif on[0] and off[0]:
        verdict = "PASS（开侧命中；关侧靠拉通道自救，推通道增量无法隔离）"
    else:
        verdict = "FAIL（开侧未命中——检查 make knowledge-index 与检索质量）"
    if degraded:
        verdict += "（检索通道异常，门禁无效）"
    print(f"冒烟结论: {verdict}")
    if degraded or not on[0]:
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except TimeoutError:
        print(f"冒烟结论: FAIL（单臂超时 {ARM_TIMEOUT_S}s——"
              f"见 runs/smoke-rag-*/trace.jsonl）")
        sys.exit(1)
