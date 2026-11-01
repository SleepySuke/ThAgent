import asyncio
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from agent_server import _sink_deltas, build_a2a_app, load_agent_by_name

CANNED = json.dumps({
    "issues": [{"file": "shop/stats.py", "line": 8, "severity": "high",
                "type": "exception", "desc": "bare except"}],
    "verdict": "request_changes", "summary": "s"})


@pytest.fixture()
def app(tmp_path):
    from harness.sandbox.manager import SandboxManager
    from harness.sandbox.worktree import WorktreeProvider

    mgr = SandboxManager(
        WorktreeProvider(allowed_cmds=frozenset({"ls"})), tmp_path / "runs")

    async def fake_run(run, prompt):
        return CANNED

    spec = replace(load_agent_by_name("cr_agent"), url="http://127.0.0.1:8101")
    return build_a2a_app(tmp_path / "runs", mgr, spec, run_agent=fake_run)


def test_agent_card_served(app):
    with TestClient(app) as c:
        r = c.get("/.well-known/agent-card.json")
        assert r.status_code == 200, r.text
        card = r.json()
        assert card["name"] == "cr_agent"
        assert card["capabilities"]["streaming"] is True


def test_jsonrpc_send_returns_task(app):
    agent_input = {"run_id": "t-svc", "node_id": "cr_agent",
                   "input_data": {"repo": "x", "commit": "main"},
                   "context_id": "t-svc", "history": []}
    with TestClient(app) as c:
        # 与 a2a 1.0 client 同协议的 JSON-RPC 调用（非流式 SendMessage；
        # SDK 方法名对齐 gRPC service，proto-json 字段名 ParseDict 兼容 camelCase）
        r = c.post("/a2a/jsonrpc", headers={"A2A-Version": "1.0"}, json={
            "jsonrpc": "2.0", "id": "1", "method": "SendMessage",
            "params": {"message": {
                "role": "ROLE_USER",
                "parts": [{"text": json.dumps(agent_input)}],
                "messageId": "m1", "contextId": "t-svc"}}})
        assert r.status_code == 200, r.text
        result = r.json().get("result", {})
        assert "error" not in r.json()
        # Task 生命周期流：非流式调用最终返回 Task（含 artifacts 或终态）
        assert result.get("kind", "task") in ("task", "message")


def test_shutdown_endpoint_is_idempotent(app):
    with TestClient(app) as c:
        r = c.post("/admin/sandboxes/never-existed/shutdown")
        assert r.status_code == 200 and r.json() == {"shutdown": "never-existed"}


def test_executor_cancel_emits_canceled_terminal_state():
    """A2A 契约：cancel() 必须把 task 推到 CANCELED 终态（否则 handler 抛
    TaskNotCancelableError）。执行体的取消由框架对 producer task 做。"""
    from types import SimpleNamespace

    from a2a.types import TaskState

    from agent_server import A2AAgentExecutor, load_agent_by_name
    from harness.sandbox.manager import SandboxManager
    from harness.sandbox.worktree import WorktreeProvider

    class Q:  # EventQueue 桩：只收集 enqueue 的事件
        def __init__(self):
            self.events = []

        async def enqueue_event(self, e):
            self.events.append(e)

    import tempfile
    from pathlib import Path
    mgr = SandboxManager(WorktreeProvider(allowed_cmds=frozenset()),
                         Path(tempfile.mkdtemp()))
    ex = A2AAgentExecutor(Path(tempfile.mkdtemp()), mgr,
                          load_agent_by_name("cr_agent"))
    q = Q()
    ctx = SimpleNamespace(task_id="t1", context_id="c1")
    import asyncio
    asyncio.run(ex.cancel(ctx, q))
    assert q.events, "cancel must enqueue at least one event"
    ev = q.events[-1]
    state = ev.status.state
    assert state == TaskState.TASK_STATE_CANCELED


def test_split_parts_separates_thought_from_answer():
    """thought part（CoT）与答案 part 拆分：答案丢失是 5.3 全挂的根因，
    此处钉死拆分契约。"""
    from types import SimpleNamespace

    from agent_server import _split_parts

    parts = [
        SimpleNamespace(text="The user wants JSON only.", thought=True),
        SimpleNamespace(text='{"issues": []}', thought=False),
        SimpleNamespace(text=None, thought=False),  # function_call part 等
    ]
    answer, thought = _split_parts(parts)
    assert answer == '{"issues": []}'
    assert thought == "The user wants JSON only."


def test_load_agent_by_name_cr():
    spec = load_agent_by_name("cr_agent")
    assert spec.name == "cr_agent"
    assert spec.artifact_name == "cr_report"
    assert callable(spec.build_agent)
    assert spec.card_path.name == "agent-card.json"


def test_load_agent_by_name_script():
    spec = load_agent_by_name("script_agent")
    assert spec.name == "script_agent"
    assert spec.artifact_name == "test_cases"
    assert callable(spec.build_agent)


def test_unknown_agent_raises():
    with pytest.raises(ValueError):
        load_agent_by_name("no_such_agent")
    with pytest.raises(ValueError):
        load_agent_by_name("case_executor")  # program 节点不是 agent


class _Part:
    def __init__(self, text, thought=False):
        self.text = text
        self.thought = thought


class _Ev:
    def __init__(self, parts):
        self.content = type("C", (), {"parts": parts})()


def test_sink_deltas_emits_text_and_thought_flag():
    out = []
    run = type("R", (), {"event_sink": staticmethod(lambda e, p: out.append((e, p)))})()
    _sink_deltas(_Ev([_Part("折扣率", thought=True), _Part("超过上限")]), run)
    assert out == [
        ("llm_delta", {"text": "折扣率", "thought": True}),
        ("llm_delta", {"text": "超过上限", "thought": False}),
    ]


def test_sink_deltas_skips_empty_and_missing():
    out = []
    run = type("R", (), {"event_sink": staticmethod(lambda e, p: out.append((e, p)))})()
    _sink_deltas(_Ev([_Part(""), _Part(None)]), run)   # 空/None 文本不 sink
    _sink_deltas(_Ev([]), run)                          # 空 parts 不 sink
    assert out == []


async def test_request_human_tool_resolves_via_registry(tmp_path):
    from harness.contract import RunContext
    from harness.tools.hitl import request_human

    run = RunContext(trace_id="t-hitl", repo_path="x", commit="d",
                     event_sink=lambda e, p: None)
    tool = request_human(run, None)
    task = asyncio.create_task(tool("折扣率上限是多少？"))
    await asyncio.sleep(0.02)
    from harness.hitl import REGISTRY
    assert REGISTRY.pending_for("t-hitl")
    assert REGISTRY.resolve("t-hitl", "0.20")
    assert await task == "0.20"


async def test_request_human_auto_answer_skips_wait(monkeypatch):
    """无人值守评测（AGENT_INFRA_HITL_AUTO）：立即确认，不注册等待不心跳。"""
    from harness.contract import RunContext
    from harness.hitl import CONFIRM_PHRASE, REGISTRY
    from harness.tools.hitl import request_human

    monkeypatch.setenv("AGENT_INFRA_HITL_AUTO", "1")
    run = RunContext(trace_id="t-hitl-auto", repo_path="x", commit="d",
                     event_sink=lambda e, p: None)
    tool = request_human(run, None)
    assert await tool("折扣率上限是多少？") == CONFIRM_PHRASE
    assert not REGISTRY.pending_for("t-hitl-auto")   # 没有挂起等待，run 不会挂死


def test_request_human_in_tool_registry():
    from harness.tools import FACTORIES
    assert "request_human" in FACTORIES


async def test_internal_hitl_route_resolves_waiter(app):
    """side 路由 404/200：resolve 必须落在 waiter 所在 event loop 的 Future 上
    （FastAPI handler 与 agent ReAct loop 同 loop，天然满足）。"""
    from httpx import ASGITransport, AsyncClient

    from harness.hitl import REGISTRY

    async with AsyncClient(transport=ASGITransport(app=app),
                           base_url="http://test") as c:
        r404 = await c.post("/internal/hitl/t-route", json={"text": "hi"})
        assert r404.status_code == 404
        assert r404.json() == {"resolved": False}
        rnull = await c.post("/internal/hitl/t-route", json={"text": None})
        assert rnull.status_code == 404  # null text 归一为 ""，不炸 500

        waiter = asyncio.create_task(REGISTRY.wait("t-route"))
        await asyncio.sleep(0.01)
        r200 = await c.post("/internal/hitl/t-route", json={"text": " 0.20 "})
        assert r200.status_code == 200
        assert r200.json() == {"resolved": True}
        assert await waiter == "0.20"


async def test_run_capped_cancels_inner_on_outer_cancel(tmp_path):
    """A2A tasks/cancel → execute 被取消时 agent 会话同步终止，不留孤儿任务
    （shield 保 inner 度过 HITL 续期，但外层真取消必须传导）。"""
    inner_cancelled = asyncio.Event()

    async def slow_run(run, prompt):
        try:
            await asyncio.sleep(30)
        except asyncio.CancelledError:
            inner_cancelled.set()
            raise
        return "x"

    from agent_server import A2AAgentExecutor

    ex = A2AAgentExecutor(tmp_path, None, None, run_agent=slow_run)
    task = asyncio.create_task(ex._run_capped(None, {}, "t", 30.0))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await asyncio.wait_for(inner_cancelled.wait(), 1), \
        "inner agent session must be cancelled together with the executor"


class _FakeSessionSvc:
    def __init__(self):
        self.store = {}
    async def get_session(self, *, app_name, user_id, session_id):
        return self.store.get(session_id)
    async def create_session(self, *, app_name, user_id, session_id=None, state=None):
        s = type("S", (), {"id": session_id})()
        self.store[session_id] = s
        return s


async def test_get_or_create_session_reuses_same_key():
    from agent_server import _get_or_create_session

    svc = _FakeSessionSvc()
    runner = type("R", (), {"session_service": svc})()
    a = await _get_or_create_session(runner, "t1:cr_agent")
    b = await _get_or_create_session(runner, "t1:cr_agent")
    c = await _get_or_create_session(runner, "t1:testing_agent")
    assert a is b                     # 同 run 同节点 → 同 session（续聊）
    assert a is not c                 # 不同节点 → 各自 session
    assert len(svc.store) == 2
