import asyncio
import json
import socket
import threading
import time

import pytest
import uvicorn

from agent_server import build_a2a_app
from harness.checkpoint import load_checkpoint, save_checkpoint
from harness.contract import AgentOutput, ExecutionPlan
from harness.engine import DEFAULT_PLAN, HarnessEngine
from harness.memory import RecallSpec
from harness.trace import Tracer

# fake_run 返回的是 agent 原始回复（契约 JSON 本体）；server 侧 parse_output
# 只认顶层 issues/verdict/summary，output_data 包装是 server 回传给 engine 的形态
CANNED = json.dumps({
    "issues": [{"file": "shop/stats.py", "line": 8, "severity": "high",
                "type": "exception", "desc": "bare except"}],
    "verdict": "request_changes", "summary": "s"})

CR_OUT = AgentOutput(
    output_data={"verdict": "request_changes", "issues": []}, artifact_url="",
    status="ok",
    artifacts=[{"artifact_id": "A001", "type": "cr_report",
                "uri": "runs/x/artifacts/cr_report.json"}])
TEST_OUT = AgentOutput(
    output_data={"cases": 2}, artifact_url="", status="ok",
    artifacts=[{"artifact_id": "A002", "type": "test_cases",
                "uri": "runs/x/artifacts/test_cases.py"}])


def _free_port() -> int:
    # a2a client 从 agent card 的 interface url 建连接（不是从传入 URL），
    # 须先定端口再写进 card，否则 card 默认指向 127.0.0.1:8101
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start(tmp_path, run_fn) -> tuple[str, uvicorn.Server, threading.Thread]:
    from dataclasses import replace

    from agent_server import load_agent_by_name
    from harness.sandbox.manager import SandboxManager
    from harness.sandbox.worktree import WorktreeProvider

    port = _free_port()
    mgr = SandboxManager(
        WorktreeProvider(allowed_cmds=frozenset()), tmp_path / "runs")
    spec = replace(load_agent_by_name("cr_agent"),
                   url=f"http://127.0.0.1:{port}")
    app = build_a2a_app(tmp_path / "runs", mgr, spec, run_agent=run_fn)
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    return f"http://127.0.0.1:{port}", server, thread


def _stop(server, thread):
    server.should_exit = True
    thread.join(timeout=5)


class _FakeEngine(HarnessEngine):
    """按 node_id 返回固定 output 的 engine：绕过真实 A2A，测调度逻辑。"""

    def __init__(self, runs_root, outputs):
        super().__init__("http://127.0.0.1:1", runs_root)
        self._outputs = outputs
        self.sent = []

    async def _send(self, node_url, agent_input, tracer, task_id_box=None,
                    budget=None):
        self.sent.append(agent_input)
        return self._outputs[agent_input.node_id]


async def test_execute_returns_trace_and_traces_events(tmp_path):
    async def fake_run(run, prompt):
        return CANNED

    url, server, thread = _start(tmp_path, fake_run)
    try:
        engine = HarnessEngine(url, tmp_path / "runs")
        trace_id = await engine.execute({"repo": "x", "commit": "defect-1"},
                                        DEFAULT_PLAN)
    finally:
        _stop(server, thread)
    trace_file = tmp_path / "runs" / trace_id / "trace.jsonl"
    events = [json.loads(line)["event"]
              for line in trace_file.read_text().splitlines()]
    assert "run_start" in events and "run_end" in events and "node_start" in events
    assert "state_transition" in events
    assert "sandbox_destroy" in events  # finally 统一回收可见


async def test_ok_status_and_report_written(tmp_path):
    async def fake_run(run, prompt):
        return CANNED

    url, server, thread = _start(tmp_path, fake_run)
    try:
        engine = HarnessEngine(url, tmp_path / "runs")
        trace_id = await engine.execute({"repo": "x", "commit": "defect-1"},
                                        DEFAULT_PLAN)
    finally:
        _stop(server, thread)
    trace = [json.loads(line) for line in
             (tmp_path / "runs" / trace_id / "trace.jsonl").read_text().splitlines()]
    node_end = next(e for e in trace if e["event"] == "node_end")
    assert node_end["payload"]["status"] == "ok"
    report = tmp_path / "runs" / trace_id / "artifacts" / "cr_report.json"
    assert report.exists()  # executor 侧落盘
    assert "a2a_task.json" in str(
        list((tmp_path / "runs" / trace_id).iterdir()))


async def test_timeout_returns_timeout_status(tmp_path):
    import asyncio

    async def slow_run(run, prompt):
        await asyncio.sleep(10)
        return CANNED

    url, server, thread = _start(tmp_path, slow_run)
    try:
        engine = HarnessEngine(url, tmp_path / "runs")
        engine.node_timeout_s = 1  # 测试压缩超时（engine 级上限生效）
        trace_id = await engine.execute({"repo": "x", "commit": "defect-1"},
                                        DEFAULT_PLAN)
    finally:
        _stop(server, thread)
    trace = [json.loads(line) for line in
             (tmp_path / "runs" / trace_id / "trace.jsonl").read_text().splitlines()]
    node_end = next(e for e in trace if e["event"] == "node_end")
    assert node_end["payload"]["status"] in ("timeout", "failed")


async def test_agent_events_forwarded_to_trace(tmp_path):
    # 回归：sink 消息含 "event" 键，engine 不得与其位置参数 event 撞名
    async def fake_run(run, prompt):
        run.event_sink("tool_call", {"tool": "read_diff"})
        run.event_sink("llm_call", {"model": "m1"})
        return CANNED

    url, server, thread = _start(tmp_path, fake_run)
    try:
        engine = HarnessEngine(url, tmp_path / "runs")
        trace_id = await engine.execute({"repo": "x", "commit": "defect-1"},
                                        DEFAULT_PLAN)
    finally:
        _stop(server, thread)
    trace = [json.loads(line) for line in
             (tmp_path / "runs" / trace_id / "trace.jsonl").read_text().splitlines()]
    tool_call = [e for e in trace if e["event"] == "tool_call"]
    assert tool_call and tool_call[0]["payload"] == {"tool": "read_diff"}
    assert any(e["event"] == "llm_call" for e in trace)
    node_end = next(e for e in trace if e["event"] == "node_end")
    assert node_end["payload"]["status"] == "ok"


async def test_unknown_node_rejected(tmp_path):
    engine = HarnessEngine("http://127.0.0.1:1", tmp_path / "runs")
    with pytest.raises(KeyError):
        await engine.execute({"repo": "x", "commit": "d"},
                             ExecutionPlan(plan_id="x",
                                           nodes=[{"id": "x", "agent": "no_such_node"}],
                                           edges=[]))


async def test_engine_rejects_empty_plan(tmp_path):
    engine = HarnessEngine("http://127.0.0.1:1", tmp_path / "runs")
    with pytest.raises(ValueError):
        await engine.execute({"repo": "x", "commit": "d"},
                             ExecutionPlan(plan_id="x", nodes=[], edges=[]))


async def test_execute_multi_node_plan(tmp_path):
    engine = _FakeEngine(tmp_path / "runs",
                         {"cr_agent": CR_OUT, "script_agent": TEST_OUT})
    plan = ExecutionPlan(plan_id="p",
                         nodes=[{"id": "cr", "agent": "cr_agent"},
                                {"id": "script", "agent": "script_agent"}],
                         edges=[["cr", "script"]])
    await engine.execute_for("t", {"repo": "x", "commit": "d"}, plan)
    # 按 plan 拓扑序调度（cr 先 script 后）
    assert [i.node_id for i in engine.sent] == ["cr_agent", "script_agent"]
    # 链式数据流：script 收到 cr 的 artifact_refs
    assert engine.sent[1].artifact_refs == CR_OUT.artifacts
    assert engine.sent[0].artifact_refs == []


async def test_program_node_dispatched_locally(tmp_path, monkeypatch):
    calls = []

    def fake_execute(runs_root, run_id, artifact_refs):
        calls.append(artifact_refs)
        return {"exit_code": 0, "stdout": "ok"}

    from harness import programs
    monkeypatch.setitem(programs.PROGRAM_HANDLERS, "execute_cases", fake_execute)
    engine = _FakeEngine(tmp_path / "runs", {})
    plan = ExecutionPlan(plan_id="p",
                         nodes=[{"id": "execute", "program": "case_executor"}],
                         edges=[])
    await engine.execute_for("t", {"repo": "x", "commit": "d"}, plan)
    assert calls == [[]]      # 本地 handler 被调用
    assert engine.sent == []  # 未走 A2A


async def test_state_transitions_emitted(tmp_path):
    engine = _FakeEngine(tmp_path / "runs", {"cr_agent": CR_OUT})
    await engine.execute_for("t", {"repo": "x", "commit": "d"}, DEFAULT_PLAN)
    trace = [json.loads(line) for line in
             (tmp_path / "runs" / "t" / "trace.jsonl").read_text().splitlines()]
    events = [e["payload"]["trigger"] for e in trace
              if e["event"] == "state_transition"]
    for expected in ("SUBMIT_TASK", "PLAN_READY", "ALL_STEPS_DONE"):
        assert expected in events
    # 首尾状态正确
    assert trace[0]["event"] == "run_start"
    assert trace[-1]["event"] == "run_end"


class _SpyMemory:
    """记录 recall/record 调用的最小 MemoryStore（结构鸭子类型）。"""

    def __init__(self, experiences):
        self._experiences = list(experiences)
        self.recalled: list[RecallSpec] = []
        self.recorded: list = []

    def recall(self, spec):
        self.recalled.append(spec)
        return list(self._experiences)

    def record(self, trace_id, output, *, context_id="", commit=""):
        self.recorded.append((trace_id, output, context_id, commit))


class _MemEngine(HarnessEngine):
    def __init__(self, runs_root, memory, output):
        super().__init__("http://127.0.0.1:1", runs_root, memory=memory)
        self._output = output
        self.sent = []

    async def _send(self, node_url, agent_input, tracer, task_id_box=None,
                    budget=None):
        self.sent.append(agent_input)
        return self._output


_EXP = [{"kind": "team_convention", "content": "折扣率上限20%", "source_run_id": ""}]


async def test_recall_injected_into_history_and_context_id_threaded(tmp_path):
    mem = _SpyMemory(_EXP)
    engine = _MemEngine(tmp_path / "runs", mem, CR_OUT)
    await engine.execute_for("t", {"repo": "x", "commit": "d", "context_id": "repo:x"},
                             DEFAULT_PLAN)
    cr_input = engine.sent[0]
    assert cr_input.history == _EXP
    assert cr_input.context_id == "repo:x"
    assert mem.recalled[0].context_id == "repo:x"
    assert mem.recalled[0].kinds == frozenset(
        {"team_convention", "past_review", "knowledge"})


async def test_record_called_with_context_and_commit(tmp_path):
    mem = _SpyMemory([])
    engine = _MemEngine(tmp_path / "runs", mem, CR_OUT)
    await engine.execute_for("t", {"repo": "x", "commit": "defect-1", "context_id": "repo:x"},
                             DEFAULT_PLAN)
    assert mem.recorded
    _trace_id, _out, ctx, commit = mem.recorded[0]
    assert ctx == "repo:x" and commit == "defect-1"
    # payload 无 context_id → 回退用 trace_id（record 路径的兜底文档化）
    mem2 = _SpyMemory([])
    engine2 = _MemEngine(tmp_path / "runs", mem2, CR_OUT)
    await engine2.execute_for("t-fallback", {"repo": "x", "commit": "defect-1"},
                              DEFAULT_PLAN)
    assert mem2.recorded[0][2] == "t-fallback"


class _RaisingMemory:
    """recall/record 都抛：memory 故障不得阻断 run（设计 §9）。"""

    def recall(self, spec):
        raise RuntimeError("recall boom")

    def record(self, trace_id, output, *, context_id="", commit=""):
        raise RuntimeError("record boom")


async def test_memory_failure_never_blocks_run(tmp_path):
    # C1：record/recall 抛异常 → 吞掉 + memory_failed 事件，run 照常完成
    engine = _MemEngine(tmp_path / "runs", _RaisingMemory(), CR_OUT)
    trace_id = await engine.execute_for("t", {"repo": "x", "commit": "d"},
                                        DEFAULT_PLAN)
    assert trace_id == "t"
    assert engine.sent[0].history == []  # recall 失败 → 空 ctx 兜底
    trace = [json.loads(line) for line in
             (tmp_path / "runs" / "t" / "trace.jsonl").read_text().splitlines()]
    phases = {e["payload"]["phase"] for e in trace
              if e["event"] == "memory_failed"}
    assert phases == {"recall", "record"}
    assert trace[-1]["event"] == "run_end"  # finally 仍走完


async def test_recall_skipped_when_node_memory_disabled(tmp_path):
    mem = _SpyMemory(_EXP)
    engine = _MemEngine(tmp_path / "runs", mem, TEST_OUT)
    plan = ExecutionPlan(plan_id="p",
                         nodes=[{"id": "t", "agent": "script_agent"}], edges=[])
    await engine.execute_for("t2", {"repo": "x", "commit": "d"}, plan)
    assert mem.recalled == []               # script_agent memory_enabled=False
    assert engine.sent[0].history == []


async def test_hitl_heartbeat_extends_node_budget(tmp_path):
    """心跳=有人在路上：hitl_heartbeat 事件到达即外推节点预算（三层 deadline）。

    预算 1s < run 总时长 2s：无续期必 node_timeout；有心跳则等人不耗预算。
    """
    import asyncio

    async def heartbeat_run(run, prompt):
        run.event_sink("hitl_heartbeat", {"trace_id": "t"})  # 立刻心跳一次
        await asyncio.sleep(2.0)  # 模拟等人：超出节点预算但不挂死
        return CANNED

    url, server, thread = _start(tmp_path, heartbeat_run)
    try:
        engine = HarnessEngine(url, tmp_path / "runs")
        engine.node_timeout_s = 1
        trace_id = await engine.execute({"repo": "x", "commit": "defect-1"},
                                        DEFAULT_PLAN)
    finally:
        _stop(server, thread)
    trace = [json.loads(line) for line in
             (tmp_path / "runs" / trace_id / "trace.jsonl").read_text().splitlines()]
    node_end = next(e for e in trace if e["event"] == "node_end")
    assert node_end["payload"]["status"] == "ok"


async def test_active_boxes_tracks_running_node(tmp_path):
    """Task 9 pause 接缝：run 进行中 _active_boxes 记录节点 url，结束即清理。"""
    seen = {}

    class ProbeEngine(_FakeEngine):
        async def _send(self, node_url, agent_input, tracer, task_id_box=None,
                        budget=None):
            entry = self._active_boxes.get(agent_input.run_id)
            seen[agent_input.run_id] = (node_url, entry, task_id_box)
            return await super()._send(node_url, agent_input, tracer,
                                       task_id_box, budget)

    engine = ProbeEngine(tmp_path / "runs", {"cr_agent": CR_OUT})
    await engine.execute_for("t", {"repo": "x", "commit": "d"}, DEFAULT_PLAN)
    url, entry, box = seen["t"]
    assert url == engine._url_for("cr_agent")
    assert entry == {"url": url, "box": box}  # box 即 _send 回填 task_id 的那一个
    assert engine._active_boxes == {}  # finally 清理，不留悬挂 entry


class _SlowEngine(HarnessEngine):
    """node 级慢 agent：给 pause 留窗口；记录重发的 node 与 input。"""

    def __init__(self, runs_root, outputs):
        super().__init__("http://127.0.0.1:1", runs_root)
        self._outputs = outputs
        self.calls = []
        self.inputs = []

    async def _send(self, node_url, agent_input, tracer, task_id_box=None,
                    budget=None):
        self.calls.append(agent_input.node_id)
        self.inputs.append(agent_input)
        await asyncio.sleep(0.3)
        return self._outputs[agent_input.node_id]


async def test_pause_mid_node_then_resume_completes(tmp_path):
    eng = _SlowEngine(tmp_path / "runs",
                      {"cr_agent": CR_OUT, "script_agent": TEST_OUT})
    plan = ExecutionPlan(plan_id="p",
                         nodes=[{"id": "cr", "agent": "cr_agent"},
                                {"id": "script", "agent": "script_agent"}],
                         edges=[["cr", "script"]])
    task = asyncio.create_task(eng.execute_for(
        "t-p1", {"repo": "x", "commit": "d"}, plan))
    await asyncio.sleep(0.1)                      # 卡在 cr 执行中
    assert await eng.pause_run("t-p1") is True
    await asyncio.sleep(0.05)
    tr = [json.loads(ln) for ln in
          (tmp_path / "runs" / "t-p1" / "trace.jsonl").read_text().splitlines()]
    assert any(e["event"] == "run_paused" for e in tr)
    assert eng.resume_run("t-p1", text="重点看折扣逻辑")
    await task                                    # 恢复后跑完
    tr = [json.loads(ln) for ln in
          (tmp_path / "runs" / "t-p1" / "trace.jsonl").read_text().splitlines()]
    assert any(e["event"] == "run_resumed" for e in tr)
    assert [c for c in eng.calls].count("script_agent") == 1


async def test_resume_skips_completed_nodes(tmp_path):
    """两节点：cr 已完成、script 慢 → pause 在 script；resume 不重发 cr。"""
    eng = _SlowEngine(tmp_path / "runs",
                      {"cr_agent": CR_OUT, "script_agent": TEST_OUT})
    plan = ExecutionPlan(plan_id="p",
                         nodes=[{"id": "cr", "agent": "cr_agent"},
                                {"id": "script", "agent": "script_agent"}],
                         edges=[["cr", "script"]])
    task = asyncio.create_task(eng.execute_for(
        "t-p2", {"repo": "x", "commit": "d"}, plan))
    await asyncio.sleep(0.45)                      # cr 完成（0.3s），script 进行中
    assert await eng.pause_run("t-p2") is True
    await asyncio.sleep(0.05)
    n_cr = eng.calls.count("cr_agent")
    assert n_cr == 1
    eng.resume_run("t-p2")
    await task
    assert eng.calls.count("cr_agent") == 1        # 完成节点不重跑
    assert eng.calls.count("script_agent") >= 1   # 当前节点重跑（同 session 续聊）


async def test_resume_injects_feedback_into_current_node(tmp_path):
    eng = _SlowEngine(tmp_path / "runs", {"cr_agent": CR_OUT})
    task = asyncio.create_task(eng.execute_for(
        "t-p3", {"repo": "x", "commit": "d"}, DEFAULT_PLAN))
    await asyncio.sleep(0.1)
    await eng.pause_run("t-p3")
    eng.resume_run("t-p3", text="补充：关注空指针")
    await task
    assert eng.inputs[-1].hitl_feedback == {"text": "补充：关注空指针"}


async def test_resume_empty_feedback_does_not_leak_previous(tmp_path):
    """连续两次 pause/resume：第一次带意见、第二次留空——第二次重发的节点
    不得再看到第一次的意见（hitl_feedback 每次 resume 必须覆写）。"""
    eng = _SlowEngine(tmp_path / "runs", {"cr_agent": CR_OUT})
    task = asyncio.create_task(eng.execute_for(
        "t-fb", {"repo": "x", "commit": "d"}, DEFAULT_PLAN))
    await asyncio.sleep(0.1)
    await eng.pause_run("t-fb")
    eng.resume_run("t-fb", text="补充：关注空指针")
    await asyncio.sleep(0.1)                 # 节点带意见重跑中
    await eng.pause_run("t-fb")
    eng.resume_run("t-fb")                   # 空意见 resume
    await task
    assert eng.inputs[-2].hitl_feedback == {"text": "补充：关注空指针"}
    assert eng.inputs[-1].hitl_feedback is None


async def test_pause_returns_false_when_body_completes_during_cancel(tmp_path):
    """TOCTOU：cancel 的 HTTP 往返期间 body 跑完 → 如实返回 False（非 True）。"""
    node_active = asyncio.Event()
    in_cancel = asyncio.Event()
    body_done = asyncio.Event()

    class RaceEngine(HarnessEngine):
        async def _send(self, node_url, agent_input, tracer, task_id_box=None,
                        budget=None):
            node_active.set()        # _active_boxes 已就位，可以发 pause 了
            await in_cancel.wait()   # 卡住：pause 进入 cancel 往返时 body 未完
            return CR_OUT

        async def _cancel_task(self, node_url, task_id_box, tracer):
            in_cancel.set()          # 模拟往返期间 body 继续推进并完成
            await body_done.wait()

    eng = RaceEngine("http://127.0.0.1:1", tmp_path / "runs")
    task = asyncio.create_task(eng.execute_for(
        "t-race", {"repo": "x", "commit": "d"}, DEFAULT_PLAN))
    await node_active.wait()         # 等 body 真正进入节点执行（entry 已建）
    pause_task = asyncio.create_task(eng.pause_run("t-race"))
    await in_cancel.wait()           # pause 已进入 cancel 往返
    await task                       # body 在往返窗口内自然完成
    body_done.set()                  # 放行往返，pause_run 此时复查 done
    assert await pause_task is False


async def test_pause_unknown_trace_returns_false(tmp_path):
    eng = _SlowEngine(tmp_path / "runs", {"cr_agent": CR_OUT})
    assert await eng.pause_run("nope") is False
    assert eng.resume_run("nope") is False


async def test_resume_infers_progress_from_trace_when_checkpoint_broken(tmp_path):
    eng = _SlowEngine(tmp_path / "runs",
                      {"cr_agent": CR_OUT, "script_agent": TEST_OUT})
    plan = ExecutionPlan(plan_id="p",
                         nodes=[{"id": "cr", "agent": "cr_agent"},
                                {"id": "script", "agent": "script_agent"}],
                         edges=[["cr", "script"]])
    task = asyncio.create_task(eng.execute_for(
        "t-inf", {"repo": "x", "commit": "d"}, plan))
    await asyncio.sleep(0.45)
    await eng.pause_run("t-inf")
    await asyncio.sleep(0.05)
    # 破坏 checkpoint（模拟损坏）
    (tmp_path / "runs" / "t-inf" / "checkpoint.json").write_text(
        "{corrupted", encoding="utf-8")
    eng.resume_run("t-inf")
    await task
    assert eng.calls.count("cr_agent") == 1     # 从 trace 推断出 cr 已完成，不重跑


async def test_inference_writes_back_healed_checkpoint(tmp_path):
    runs = tmp_path / "runs"
    tr = Tracer(runs, "t-inf2")
    tr.emit("node_end", node_id="cr", status="ok")
    plan = ExecutionPlan(plan_id="p",
                         nodes=[{"id": "cr", "agent": "cr_agent"}], edges=[])
    completed, _outputs = HarnessEngine._completed_from_disk(runs, "t-inf2", plan)
    assert completed == ["cr"]
    cp = load_checkpoint(runs, "t-inf2")
    assert cp is not None and "cr" in cp["completed_nodes"]   # 自愈写回


async def test_checkpoint_progress_filtered_to_current_plan(tmp_path):
    """同 trace_id 换 plan 重跑：checkpoint 里旧 plan 的陈旧节点 id 与结论
    不泄入续跑的 upstream/artifact 链。"""
    runs = tmp_path / "runs"
    save_checkpoint(runs, "t-stale", {
        "run_id": "t-stale", "context_id": "repo:x", "current_node": None,
        "harness_state": "executing",
        "completed_nodes": ["old_node", "cr"],
        "node_outputs": {"old_node": {"output_data": {"recovered": True}},
                         "cr": {"output_data": {"ok": 1}}},
        "version": 1, "created_at": time.time()})
    plan = ExecutionPlan(plan_id="p",
                         nodes=[{"id": "cr", "agent": "cr_agent"}], edges=[])
    completed, outputs = HarnessEngine._completed_from_disk(runs, "t-stale", plan)
    assert completed == ["cr"]           # 旧 plan 的 old_node 被滤掉
    assert "old_node" not in outputs     # 其结论不进 upstream/artifact 链
    assert outputs["cr"]["output_data"] == {"ok": 1}


async def test_double_resume_second_rejected(tmp_path):
    """双窗口竞态守卫：resume 已 set 未被引擎消费时，第二次 resume 拒绝覆写
    feedback（预研 §四层二）。"""
    eng = _SlowEngine(tmp_path / "runs", {"cr_agent": CR_OUT})
    task = asyncio.create_task(eng.execute_for(
        "t-dr", {"repo": "x", "commit": "d"}, DEFAULT_PLAN))
    await asyncio.sleep(0.1)
    await eng.pause_run("t-dr")
    assert eng.resume_run("t-dr", text="方案一") is True
    assert eng.resume_run("t-dr", text="方案二") is False   # 已 set 未消费
    await task
    assert eng.inputs[-1].hitl_feedback == {"text": "方案一"}


async def test_shutdown_sandboxes_broadcasts_all_participating_urls(tmp_path):
    """层1 防线：shutdown 广播该 run 全部参与节点 url（只发主 server 是跨
    server 回收盲点，预研 §3.1），同 url 去重各只发一次。"""
    import httpx

    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200)

    eng = _FakeEngine(tmp_path / "runs",
                      {"cr_agent": CR_OUT, "script_agent": TEST_OUT})
    eng._url_overrides = {"cr_agent": "http://a:9001",
                          "script_agent": "http://b:9002"}
    eng._http = httpx.AsyncClient(transport=httpx.MockTransport(handler),
                                  trust_env=False)  # 坑 #11：不打系统代理
    plan = ExecutionPlan(plan_id="p",
                         nodes=[{"id": "cr", "agent": "cr_agent"},
                                {"id": "script", "agent": "script_agent"}],
                         edges=[["cr", "script"]])
    await eng.execute_for("t-bc", {"repo": "x", "commit": "d"}, plan)
    assert sorted(seen) == ["http://a:9001/admin/sandboxes/t-bc/shutdown",
                            "http://b:9002/admin/sandboxes/t-bc/shutdown"]
    await eng._http.aclose()


async def test_paused_runs_merges_disk_checkpoints(tmp_path):
    """磁盘挂起扫描：进程重启后内存 registry 已空，磁盘 checkpoint 仍可见。"""
    runs = tmp_path / "runs"
    save_checkpoint(runs, "t-disk", {
        "run_id": "t-disk", "context_id": "repo:x", "current_node": "cr",
        "harness_state": "paused", "completed_nodes": [], "node_outputs": {},
        "version": 1, "created_at": time.time()})
    (runs / "t-bad").mkdir(parents=True)
    (runs / "t-bad" / "checkpoint.json").write_text("{oops", encoding="utf-8")
    eng = _SlowEngine(runs, {"cr_agent": CR_OUT})
    assert eng.paused_runs("repo:x") == [
        {"trace_id": "t-disk", "current_node": "cr", "context_id": "repo:x"}]
