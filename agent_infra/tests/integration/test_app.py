import json

from starlette.testclient import TestClient

from app import create_app


class FakeEngine:
    """与 HarnessEngine 同签名（execute/execute_for），落盘行为对齐。"""

    def __init__(self, runs_root):
        self.runs_root = runs_root
        self.calls = []

    async def execute(self, payload, plan=None):
        trace_id = f"fake-{len(self.calls) + 1}"
        await self.execute_for(trace_id, payload, plan)
        return trace_id

    async def execute_for(self, trace_id, payload, plan=None):
        self.calls.append(payload)
        runs = self.runs_root / trace_id
        runs.mkdir(parents=True, exist_ok=True)
        (runs / "trace.jsonl").write_text(json.dumps(
            {"event": "run_start", "payload": {}}) + "\n")
        (runs / "artifacts").mkdir(exist_ok=True)
        (runs / "artifacts" / "cr_report.json").write_text(json.dumps(
            {"issues": [], "verdict": "approve", "summary": "s"}))


def test_commits_lists_defects(tmp_path):
    app = create_app(engine=None, fixture_repo=tmp_path, runs_root=tmp_path)
    with TestClient(app) as c:
        r = c.get("/commits")
        assert r.status_code == 200
        tags = [x["tag"] for x in r.json()]
        assert tags == ["defect-1", "defect-2", "defect-3", "defect-4", "defect-5"]


def test_run_flow_with_fake_engine(tmp_path):
    import time

    fake = FakeEngine(tmp_path / "runs")
    app = create_app(engine=fake, fixture_repo=tmp_path, runs_root=tmp_path / "runs")
    with TestClient(app) as c:
        r = c.post("/runs", json={"commit": "defect-1"})
        trace_id = r.json()["trace_id"]
        ev = []
        for _ in range(20):  # 后台 task 落盘轮询
            ev = c.get(f"/runs/{trace_id}/events").json()
            if ev:
                break
            time.sleep(0.1)
        assert ev  # 事件时间线可取
        r2 = c.get(f"/runs/{trace_id}")
        assert r2.json()["status"] in ("running", "ok")


def test_run_failure_surfaces_error(tmp_path):
    import time

    class BoomEngine(FakeEngine):
        async def execute_for(self, trace_id, payload, plan=None):
            raise RuntimeError("engine exploded")

    app = create_app(engine=BoomEngine(tmp_path / "runs"),
                     fixture_repo=tmp_path, runs_root=tmp_path / "runs")
    with TestClient(app) as c:
        trace_id = c.post("/runs", json={"commit": "defect-1"}).json()["trace_id"]
        body = {}
        for _ in range(20):  # 后台 task 写 error.txt 轮询
            body = c.get(f"/runs/{trace_id}").json()
            if body.get("status") == "failed":
                break
            time.sleep(0.1)
        assert body["status"] == "failed"
        assert "engine exploded" in body["error"]
        assert body["report"] is None


def test_index_served(tmp_path):
    app = create_app(engine=None, fixture_repo=tmp_path, runs_root=tmp_path)
    with TestClient(app) as c:
        assert "Agent Infra" in c.get("/").text


def test_run_status_failed_via_trace_run_end(tmp_path):
    """engine 只在成功时写 a2a_task.json；失败要看 trace.jsonl 的 run_end。"""
    app = create_app(engine=None, fixture_repo=tmp_path, runs_root=tmp_path)
    run_dir = tmp_path / "trace-1"
    run_dir.mkdir(parents=True)
    (run_dir / "trace.jsonl").write_text(
        json.dumps({"event": "run_start", "payload": {}}) + "\n" +
        json.dumps({"event": "run_end", "payload": {"status": "failed"}}) + "\n")
    with TestClient(app) as c:
        r = c.get("/runs/trace-1")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "failed"
        assert body["report"] is None
        assert body["error"] == "see trace.jsonl"


def make_app_client(tmp_path):
    """无 engine 依赖的只读端点测试客户端（/commits、/dag 等）。"""
    app = create_app(engine=None, fixture_repo=tmp_path, runs_root=tmp_path)
    return TestClient(app), tmp_path


def test_dag_returns_registry_graph(tmp_path):
    c, _ = make_app_client(tmp_path)
    r = c.get("/dag")
    assert r.status_code == 200
    g = r.json()
    ids = {n["id"] for n in g["nodes"]}
    assert "planning_agent" in ids and "case_executor" in ids
    types = {n["id"]: n["type"] for n in g["nodes"]}
    assert types["cr_agent"] == "agent" and types["case_executor"] == "program"
    assert {"from": "cr_agent", "to": "test_recall_agent"} in g["edges"]
    assert {"from": "script_agent", "to": "case_executor"} in g["edges"]


def test_run_artifacts_endpoint_includes_program_result(tmp_path):
    """节点产物端点：返回 artifacts/ 文件 + program 节点执行结果。"""
    app = create_app(engine=None, fixture_repo=tmp_path, runs_root=tmp_path)
    run_dir = tmp_path / "r1"
    (run_dir / "artifacts").mkdir(parents=True)
    (run_dir / "artifacts" / "cr_report.json").write_text('{"verdict": "approve"}')
    (run_dir / "checkpoint.json").write_text(json.dumps(
        {"node_outputs": {"execute": {"output_data": {"exit_code": 0}}}}))
    with TestClient(app) as c:
        names = {a["name"] for a in c.get("/runs/r1/artifacts").json()}
        assert "cr_report.json" in names
        assert "execute_result.json" in names  # program 节点结果从 checkpoint 取


def test_stream_yields_events_then_end(tmp_path):
    c, runs = make_app_client(tmp_path)
    tid = "t-stream-1"
    d = runs / tid
    d.mkdir(parents=True)
    (d / "trace.jsonl").write_text(
        '{"event":"run_start"}\n{"event":"node_start"}\n', encoding="utf-8")
    with c.stream("GET", f"/runs/{tid}/stream") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(chunk for chunk in r.iter_text())
    assert "event: trace" in body and '"run_start"' in body
    # 追加终态后重开：先补发增量，再见 end 关流
    (d / "trace.jsonl").write_text(
        '{"event":"run_start"}\n{"event":"node_start"}\n'
        '{"event":"run_end","payload":{"status":"ok"}}\n', encoding="utf-8")
    with c.stream("GET", f"/runs/{tid}/stream") as r:
        body = "".join(chunk for chunk in r.iter_text())
    assert '"run_end"' in body and "event: end" in body


def test_stream_resumes_from_last_event_id(tmp_path):
    c, runs = make_app_client(tmp_path)
    tid = "t-stream-2"
    d = runs / tid
    d.mkdir(parents=True)
    (d / "trace.jsonl").write_text('{"event":"a"}\n{"event":"b"}\n', encoding="utf-8")
    with c.stream("GET", f"/runs/{tid}/stream",
                  headers={"Last-Event-ID": "1"}) as r:
        body = "".join(chunk for chunk in r.iter_text())
    assert '"a"' not in body and '"b"' in body and 'id: 2' in body


def test_stream_404_unknown_run(tmp_path):
    c, _ = make_app_client(tmp_path)
    assert c.get("/runs/nope/stream").status_code == 404


def test_hitl_forward_unknown_run(tmp_path):
    c, _ = make_app_client(tmp_path)
    r = c.post("/runs/nope/hitl", json={"text": "x"})
    assert r.status_code == 404
    assert r.json() == {"error": "no such run"}


def test_pause_unknown_run_404(tmp_path):
    c, _ = make_app_client(tmp_path)
    assert c.post("/runs/nope/pause").status_code == 404


def test_resume_unknown_run_404(tmp_path):
    c, _ = make_app_client(tmp_path)
    assert c.post("/runs/nope/resume", json={"text": ""}).status_code == 404


def test_hitl_forward_resolves_pending(tmp_path):
    """转发成功路径：答案广播到各 agent server，首个 resolve 成功的胜出。

    真实 server + request_human 闭环由 Task 13 e2e 覆盖；此处打桩验证转发约定。
    """
    import socket
    import threading
    import time

    import uvicorn
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse

    def _free_port() -> int:
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            return s.getsockname()[1]

    port = _free_port()
    stub = FastAPI()

    @stub.post("/internal/hitl/{trace_id}")
    def answer(trace_id: str, body: dict) -> JSONResponse:
        # 与 agent_server /internal/hitl 同契约：无 waiter → 404
        ok = trace_id == "t1"
        return JSONResponse({"resolved": ok}, status_code=200 if ok else 404)

    server = uvicorn.Server(uvicorn.Config(
        stub, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)

    class HitlEngine(FakeEngine):
        def node_urls(self):
            return [f"http://127.0.0.1:{port}", "http://127.0.0.1:1"]

    app = create_app(engine=HitlEngine(tmp_path / "runs"),
                     fixture_repo=tmp_path, runs_root=tmp_path / "runs")
    for tid in ("t1", "t2"):
        (tmp_path / "runs" / tid).mkdir(parents=True)
    try:
        with TestClient(app) as c:
            r = c.post("/runs/t1/hitl", json={"text": "折扣率按 8 折"})
            assert r.status_code == 200
            assert r.json() == {"resolved": True,
                                "server": f"http://127.0.0.1:{port}"}
            # 两个 server 都不接（404 / 连不上）→ 无 pending hitl
            r2 = c.post("/runs/t2/hitl", json={"text": "x"})
            assert r2.status_code == 404
            assert r2.json() == {"error": "no pending hitl"}
    finally:
        server.should_exit = True


class IntakeEngine(FakeEngine):
    """补齐 intent 路由所需的最小同签名方法。"""

    def __init__(self, runs_root, paused):
        super().__init__(runs_root)
        self.paused = paused
        self.resume_ok = True
        self.resumed = []

    def paused_runs(self, context_id):
        return self.paused

    def resume_run(self, trace_id, text=""):
        if not self.resume_ok:
            return False
        if trace_id not in {p["trace_id"] for p in self.paused}:
            return False
        self.resumed.append((trace_id, text))
        return True


def _message_client(tmp_path, paused):
    from app import create_app
    app = create_app(engine=IntakeEngine(tmp_path / "runs", paused),
                     fixture_repo=tmp_path, runs_root=tmp_path / "runs")
    return TestClient(app)


PAUSED = [{"trace_id": "aaa", "current_node": "cr",
           "context_id": "repo:demo_repo"}]


def test_session_message_resume(tmp_path, monkeypatch):
    def fake_complete(prompt):
        return '{"intent":"resume","trace_id":"aaa"}'
    monkeypatch.setattr("harness.intake._default_complete", fake_complete)
    with _message_client(tmp_path, PAUSED) as c:
        r = c.post("/session/repo:demo_repo/message", json={"query": "继续"})
    assert r.status_code == 200
    assert r.json() == {"intent": "resume", "trace_id": "aaa"}


def test_session_message_fallback_409(tmp_path, monkeypatch):
    def boom(prompt):
        raise RuntimeError("llm down")
    monkeypatch.setattr("harness.intake._default_complete", boom)
    with _message_client(tmp_path, PAUSED) as c:
        r = c.post("/session/repo:demo_repo/message", json={"query": "继续"})
    assert r.status_code == 409
    assert r.json() == {"fallback": True, "candidates": PAUSED}


def test_session_message_other_context_filtered(tmp_path, monkeypatch):
    """挂起 run 属于别的 context → 视为无挂起，直接 new，不触发识别。"""
    def fail(prompt):
        raise AssertionError("llm should not be called")
    monkeypatch.setattr("harness.intake._default_complete", fail)
    with _message_client(tmp_path, PAUSED) as c:
        r = c.post("/session/repo:other/message", json={"query": "x"})
    assert r.status_code == 200
    assert r.json() == {"intent": "new"}


def test_session_message_resume_target_gone_409(tmp_path, monkeypatch):
    """识别后 run 已在别处被恢复（classify 与 resume 间的竞态）→ 409。"""
    def fake_complete(prompt):
        return '{"intent":"resume","trace_id":"aaa"}'
    monkeypatch.setattr("harness.intake._default_complete", fake_complete)
    with _message_client(tmp_path, PAUSED) as c:
        c.app.state.engine.resume_ok = False
        r = c.post("/session/repo:demo_repo/message", json={"query": "继续"})
    assert r.status_code == 409
    assert r.json() == {"error": "run not paused"}


def test_session_message_default_llm_path_runs(tmp_path, monkeypatch):
    """async handler + 默认 LLM 通路：to_thread 里同步 completion 照常跑通。"""
    def fake_completion(model, messages):
        assert "挂起任务列表" in messages[0]["content"]
        return {"choices": [{"message": {"content":
                '{"intent":"resume","trace_id":"aaa"}'}}]}
    monkeypatch.setattr("litellm.completion", fake_completion)
    with _message_client(tmp_path, PAUSED) as c:
        r = c.post("/session/repo:demo_repo/message", json={"query": "继续"})
    assert r.status_code == 200
    assert r.json() == {"intent": "resume", "trace_id": "aaa"}


def test_run_status_review_pending_face(tmp_path):
    """V2c-2：checkpoint 审阅态优先于 cr_report 判定（否则报告已出即误判 ok）。"""
    import time as _t

    from harness.checkpoint import save_checkpoint
    app = create_app(engine=None, fixture_repo=tmp_path, runs_root=tmp_path)
    d = tmp_path / "t-rev"
    (d / "artifacts").mkdir(parents=True)
    (d / "artifacts" / "cr_report.json").write_text('{"verdict": "approve"}')
    (d / "artifacts" / "execution_report.md").write_text("# 报告", encoding="utf-8")
    save_checkpoint(tmp_path, "t-rev", {
        "run_id": "t-rev", "context_id": "repo:demo_repo",
        "current_node": "report", "harness_state": "review_pending",
        "completed_nodes": [], "node_outputs": {}, "round": 2,
        "version": 2, "created_at": _t.time()})
    with TestClient(app) as c:
        st = c.get("/runs/t-rev").json()
        assert st["status"] == "review_pending"
        assert st["round"] == 2
        assert st["report"] == "# 报告"


async def test_session_message_serialized_per_context(tmp_path, monkeypatch):
    """裁定 11：同 context 并发 message 一次只处理一条（无交错）。"""
    import asyncio

    import httpx

    order: list[str] = []

    def fake_classify(query, paused):
        # sync fake（handler 经 to_thread 调用）：线程池里可交错，锁不住则乱序
        import time
        order.append("in")
        time.sleep(0.05)
        order.append("out")
        return {"intent": "new"}

    monkeypatch.setattr("harness.intake.classify_intent", fake_classify)
    app = create_app(engine=IntakeEngine(tmp_path / "runs", PAUSED),
                     fixture_repo=tmp_path, runs_root=tmp_path / "runs")
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport,
                                 base_url="http://t") as cli:
        await asyncio.gather(*[
            cli.post("/session/repo:demo_repo/message", json={"query": "x"})
            for _ in range(2)])
    assert order == ["in", "out", "in", "out"]   # 无交错 = 锁生效
