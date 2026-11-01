"""E2E：RAG 双通道——推（recall 注入 knowledge 段）/ 拉（search_knowledge
工具事件跨进程落 trace）。fake agent / 脚本化工具调用，不烧真实 LLM。"""
from __future__ import annotations

import json

from harness.engine import DEFAULT_PLAN, HarnessEngine
from harness.knowledge import KnowledgeBase
from harness.memory import HybridMemory, TfidfEmbedder
from tests.e2e.test_memory_ab import CANNED, _FakeServer, _free_port


def _corpus(tmp_path, text: str):
    d = tmp_path / "knowledge"
    d.mkdir(exist_ok=True)
    (d / "discount-policy.md").write_text(text, encoding="utf-8")
    return d


async def test_push_channel_injects_knowledge_into_prompt(tmp_path):  # 矩阵 #14
    runs = tmp_path / "runs"
    corpus = _corpus(tmp_path, "# 折扣规范\n大促全场折扣率上限 0.20，0.30 须审批")
    conv = tmp_path / "conventions.json"
    conv.write_text("[]", encoding="utf-8")  # 隔离三期种子：增量即知识层
    seen: dict = {}

    async def cr_run(run, prompt):
        seen["prompt"] = prompt
        return CANNED

    srv = _FakeServer(runs, cr_run, _free_port())
    srv.start()
    try:
        engine = HarnessEngine(
            None, runs,
            memory=HybridMemory(
                runs, conv,
                knowledge=KnowledgeBase(runs, corpus, embedder=TfidfEmbedder())),
            agent_urls={"cr_agent": f"http://127.0.0.1:{srv.port}"})
        await engine.execute_for(
            "e2e-rag-push", {"repo": "x", "commit": "defect-5",
                             "context_id": "repo:x"}, DEFAULT_PLAN)
    finally:
        srv.stop()

    assert "0.20" in seen["prompt"]                 # 知识摘录进 prompt（history）
    assert '"knowledge"' in seen["prompt"]          # kind 标注（注入段可辨识）


async def test_pull_channel_tool_events_reach_trace(tmp_path, monkeypatch):  # #15
    from harness.tools import knowledge as tk

    runs = tmp_path / "runs"
    corpus = _corpus(tmp_path, "# 折扣规范\n大促全场统一折扣率上限 20%（rate <= 0.20）")
    monkeypatch.setattr(
        tk, "_KB", KnowledgeBase(runs, corpus, embedder=TfidfEmbedder()))
    seen: dict = {}

    async def cr_run(run, prompt):
        # 脚本化 fake LLM：像 ADK ReAct 一样调工具并把工具事件外发
        tool = tk.search_knowledge(run, None)
        run.event_sink("tool_call", {"tool": "search_knowledge", "call_id": "c1",
                                     "args": "{'query': '折扣率上限'}"})
        out = await tool("折扣率上限是多少")
        run.event_sink("tool_result", {"tool": "search_knowledge", "call_id": "c1",
                                       "result": out[:300]})
        seen["out"] = out
        return CANNED

    srv = _FakeServer(runs, cr_run, _free_port())
    srv.start()
    try:
        engine = HarnessEngine(
            None, runs, agent_urls={"cr_agent": f"http://127.0.0.1:{srv.port}"})
        await engine.execute_for("e2e-rag-pull",
                                 {"repo": "x", "commit": "defect-1"}, DEFAULT_PLAN)
    finally:
        srv.stop()

    assert "discount-policy.md" in seen["out"] and "0.20" in seen["out"]
    trace = [json.loads(line) for line in
             (runs / "e2e-rag-pull" / "trace.jsonl").read_text().splitlines()]
    tools = [e for e in trace if e["event"] in ("tool_call", "tool_result")]
    assert any(e["payload"]["tool"] == "search_knowledge"
               for e in tools)                     # 工具事件跨进程落 trace
