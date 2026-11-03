"""Task 5：intake 扩展——挂起候选并入 review_pending（审阅语义）。

①paused_runs 磁盘分支含 review_pending 条目且带 state 字段；内存分支同理。
②classify_intent 的 _SYSTEM 文本含 state 教学（钉字符串）。
③fallback candidates 透传 state（前端二选一卡可显示状态）。
"""
import asyncio
import time

from harness.checkpoint import save_checkpoint
from harness.engine import HarnessEngine
from harness.intake import _SYSTEM, classify_intent


def test_paused_runs_disk_includes_review_pending_with_state(tmp_path):
    runs = tmp_path / "runs"
    save_checkpoint(runs, "t-rev", {
        "run_id": "t-rev", "context_id": "repo:x", "current_node": "report",
        "harness_state": "review_pending", "completed_nodes": [],
        "node_outputs": {}, "round": 2, "version": 2,
        "created_at": time.time()})
    save_checkpoint(runs, "t-pause", {
        "run_id": "t-pause", "context_id": "repo:x", "current_node": "cr",
        "harness_state": "paused", "completed_nodes": [],
        "node_outputs": {}, "version": 2, "created_at": time.time()})
    eng = HarnessEngine(None, runs)
    got = {p["trace_id"]: p for p in eng.paused_runs("repo:x")}
    assert got["t-rev"]["state"] == "review_pending"
    assert got["t-rev"]["current_node"] == "report"
    assert got["t-pause"]["state"] == "paused"


def test_paused_runs_memory_branch_review_state(tmp_path):
    eng = HarnessEngine(None, tmp_path)
    # 内存分支：直接构造 handle（review_event 待消费 → review_pending）
    from harness.engine import _RunHandle
    handle = _RunHandle(trace_id="t1")
    handle.review_event = asyncio.Event()
    handle.current_node = "report"
    eng._runs["t1"] = handle
    (out,) = eng.paused_runs("repo:x")
    assert out == {"trace_id": "t1", "current_node": "report",
                   "state": "review_pending"}


def test_classify_intent_system_prompt_teaches_state():
    # 钉字符串：路由 LLM 必须知道 state 字段的两种语义
    assert "review_pending" in _SYSTEM
    assert "paused" in _SYSTEM
    assert "裁决" in _SYSTEM or "接受" in _SYSTEM


def test_fallback_candidates_carry_state(tmp_path):
    paused = [{"trace_id": "t-rev", "current_node": "report",
               "state": "review_pending", "context_id": "repo:x"}]

    def boom(prompt):
        raise RuntimeError("llm down")
    out = classify_intent("继续", paused, complete=boom)
    assert out == {"intent": "fallback", "candidates": paused}
    assert out["candidates"][0]["state"] == "review_pending"


def test_resume_routing_still_works_for_review_pending():
    paused = [{"trace_id": "t-rev", "current_node": "report",
               "state": "review_pending", "context_id": "repo:x"}]
    out = classify_intent("接受之前那份报告", paused,
                          complete=lambda p: '{"intent":"resume","trace_id":"t-rev"}')
    assert out == {"intent": "resume", "trace_id": "t-rev"}
