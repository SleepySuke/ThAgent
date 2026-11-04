"""FastAPI 入口（harness 侧）。ADK 由 agent server 承载，调度权威是自建 engine。"""
from __future__ import annotations

import asyncio
import json
import subprocess
import uuid
from pathlib import Path
from typing import Literal

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel

from eval.evaluate import evaluate_report, load_golden
from fixtures.build_demo_repo import build_demo_repo
from harness.config import runs_root as _default_runs_root
from harness.engine import DEFAULT_PLAN, HarnessEngine

ROOT = Path(__file__).parent
DEFAULT_RUNS = _default_runs_root()  # env AGENT_INFRA_RUNS_DIR 注入，默认 agent_infra/runs
DEFAULT_REPO = ROOT / "fixtures" / "demo_repo"
STREAM_IDLE_CAP = 5.0  # 秒。空转上限：无新事件就关流，EventSource 带 Last-Event-ID 自动重连


class RunRequest(BaseModel):
    commit: str
    context_note: str = ""   # 提交时人工备注（常驻被动通道，永不打断）


class HitlRequest(BaseModel):
    text: str = ""


class ResumeRequest(BaseModel):
    text: str = ""


class SessionMessage(BaseModel):
    query: str


class ReviewRequest(BaseModel):
    # 坑 #20：模型必须模块级——闭包内定义 FastAPI 解析不出
    action: Literal["accept", "replan"]
    feedback: str = ""


def create_app(engine: HarnessEngine | None = None,  # noqa: PLR0915 —— 路由闭包集中定义
               fixture_repo: Path | None = None,
               runs_root: Path | None = None) -> FastAPI:
    app = FastAPI(title="agent_infra")
    repo_path = Path(fixture_repo) if fixture_repo else DEFAULT_REPO
    runs = Path(runs_root) if runs_root else DEFAULT_RUNS
    _background_tasks: set[asyncio.Task] = set()
    # 裁定 11：per-context 串行化 v1 用 Lock（锁内 classify+路由，一次一条，
    # 语义等价 inbox）。升级路径：消息量大时换真队列 + 优先级。锁条目不
    # 回收：context 数与仓库同量级、单条 Lock 开销可忽略（t5-rev Minor）
    _ctx_locks: dict[str, asyncio.Lock] = {}

    def _spawn(coro) -> None:
        t = asyncio.create_task(coro)
        _background_tasks.add(t)
        t.add_done_callback(_background_tasks.discard)

    def ensure_repo() -> Path:
        if not (repo_path / ".git").exists():
            build_demo_repo(repo_path)
        return repo_path

    if engine is None:
        # 多 agent：base_url 留空 → 按 registry 每节点查 url（一进程一端口）
        engine = HarnessEngine(None, runs)
    # 质量打分器注入（裁定 A 组装层）：L 层 engine 不 import V 层 eval，
    # 注入点在这里——手动 accept 路径的质量分挂 review_accepted payload
    from eval.quality import score_report
    engine.quality_scorer = score_report
    app.state.engine = engine

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(ROOT / "web" / "index.html")

    @app.get("/commits")
    def commits() -> list[dict]:
        repo = ensure_repo()
        out = subprocess.run(
            ["git", "-C", str(repo), "tag", "-l", "defect-*"],
            capture_output=True, text=True, check=True).stdout.split()
        result = []
        for tag in out:
            info = subprocess.run(
                ["git", "-C", str(repo), "show", "-s", "--format=%s|%ci", tag],
                capture_output=True, text=True, check=True).stdout.strip()
            subject, date = info.split("|", 1)
            result.append({"tag": tag, "subject": subject, "date": date})
        return result

    @app.get("/dag")
    def dag() -> dict:
        """死 DAG 全集（候选图）：前端提交瞬间渲染，plan_ready 后高亮选中子集。"""
        from harness.registry import AGENT_REGISTRY, DAG_EDGES
        return {
            "nodes": [{"id": nid, "type": spec["type"]}
                      for nid, spec in AGENT_REGISTRY.items()],
            "edges": [{"from": a, "to": b} for a, b in DAG_EDGES],
        }

    @app.post("/runs")
    async def run(req: RunRequest) -> dict:
        repo = ensure_repo()
        trace_id = uuid.uuid4().hex

        async def _run():
            try:
                # plan=None → 走 planning 阶段（Planning agent 生成 ExecutionPlan）
                await engine.execute_for(
                    trace_id, {
                        "repo": str(repo), "commit": req.commit,
                        "context_note": req.context_note,
                        "context_id": f"repo:{repo.name}"})
            except Exception as e:
                import traceback
                out = runs / trace_id
                out.mkdir(parents=True, exist_ok=True)
                # ponytail: 全 traceback 而非 str(e)——只留一行时排查信息量不够
                (out / "error.txt").write_text(
                    f"{e}\n{traceback.format_exc()}")

        _spawn(_run())
        return {"trace_id": trace_id}

    @app.get("/runs/{trace_id}")
    def run_status(trace_id: str):
        err = runs / trace_id / "error.txt"
        if err.exists():
            return {"status": "failed", "report": None,
                    "error": err.read_text()}
        # 审阅面（V2c-2）：report 已出但等人裁决——必须先于 cr_report 判定，
        # 否则报告落盘即误判 "ok"。无 execution_report.md 的旧链 report=None。
        cp = runs / trace_id / "checkpoint.json"
        if cp.exists():
            try:
                data = json.loads(cp.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                data = {}
            if data.get("harness_state") == "review_pending":
                md = runs / trace_id / "artifacts" / "execution_report.md"
                return {"status": "review_pending",
                        "round": data.get("round", 1),
                        "report": md.read_text(encoding="utf-8")
                        if md.exists() else None}
        report = runs / trace_id / "artifacts" / "cr_report.json"
        done = report.exists()
        if done:
            return {"status": "ok", "report": json.loads(report.read_text())}
        # engine 写过 run_end 但无报告 → 失败（否则永远 "running"）
        trace = runs / trace_id / "trace.jsonl"
        if trace.exists():
            for line in reversed(trace.read_text().splitlines()):
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue  # 进程中途被杀的半行，跳过
                if rec.get("event") == "run_end":
                    if rec.get("payload", {}).get("status") != "ok":
                        return {"status": "failed", "report": None,
                                "error": "see trace.jsonl"}
                    break
        return {"status": "running", "report": None}

    @app.get("/runs/{trace_id}/events")
    def run_events(trace_id: str) -> list[dict]:
        f = runs / trace_id / "trace.jsonl"
        if not f.exists():
            return []
        out = []
        for line in f.read_text().splitlines():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out

    @app.post("/runs/{trace_id}/hitl")
    async def hitl_forward(trace_id: str, req: HitlRequest):
        """人工答案 → 持有等待 Future 的 agent server（/internal/hitl 广播）。

        app 不知道 run 卡在哪个节点，逐 server 试：200 即有人接（resolve 成功）。
        """
        if not (runs / trace_id).exists():
            return JSONResponse({"error": "no such run"}, status_code=404)
        async with httpx.AsyncClient(trust_env=False, timeout=10.0) as cli:
            for base in engine.node_urls():
                try:
                    r = await cli.post(f"{base}/internal/hitl/{trace_id}",
                                       json={"text": req.text})
                    if r.status_code == 200:
                        return {"resolved": True, "server": base}
                except httpx.HTTPError:
                    continue  # server 不在/未起：试下一个
        return JSONResponse({"error": "no pending hitl"}, status_code=404)

    @app.post("/runs/{trace_id}/pause")
    async def pause(trace_id: str):
        if not (runs / trace_id).exists():
            return JSONResponse({"error": "no such run"}, status_code=404)
        ok = await engine.pause_run(trace_id)
        return ({"paused": True} if ok
                else JSONResponse({"error": "run not active"}, status_code=409))

    @app.post("/runs/{trace_id}/resume")
    async def resume(trace_id: str, req: ResumeRequest):
        if not (runs / trace_id).exists():
            return JSONResponse({"error": "no such run"}, status_code=404)
        ok = engine.resume_run(trace_id, req.text)
        return ({"resumed": True} if ok
                else JSONResponse({"error": "run not paused"}, status_code=409))

    @app.get("/session/{context_id}/paused")
    def session_paused(context_id: str) -> list[dict]:
        return engine.paused_runs(context_id)

    @app.post("/session/{context_id}/message")
    async def session_message(context_id: str, req: SessionMessage):
        """新 query 意图路由：resume 已挂起 run / 新任务 / fallback 二选一。

        async handler：resume_run 里 resume_event.set() 必须发生在事件循环
        线程（threadpool 线程改 asyncio 状态属越界）；阻塞的 LLM 分类经
        asyncio.to_thread 移出事件循环。

        全程持 per-context 锁：同会话并发消息一次只处理一条（裁定 11）。
        """
        async with _ctx_locks.setdefault(context_id, asyncio.Lock()):
            from harness.intake import classify_intent
            # engine 不按 context_id 过滤（内存条目无此字段），调用方自行筛（缺省=本会话）
            paused = [p for p in engine.paused_runs(context_id)
                      if p.get("context_id", context_id) == context_id]
            out = await asyncio.to_thread(classify_intent, req.query, paused)
            if out["intent"] == "fallback":
                return JSONResponse(
                    {"fallback": True, "candidates": out["candidates"]},
                    status_code=409)
            if out["intent"] == "resume":
                # review_pending 的「接受」经聊天直达审阅 accept（t5-rev
                # Important：否则 resume_run 对审阅态恒 False → 409，教学
                # 承诺脱节）；带修改意见的重做走页面审阅卡（需 feedback 输入）
                entry = next((p for p in paused
                              if p["trace_id"] == out["trace_id"]), {})
                if entry.get("state") == "review_pending":
                    ok = engine.review_run(out["trace_id"], "accept")
                    if not ok:
                        return JSONResponse(
                            {"error": "run not awaiting review"},
                            status_code=409)
                    return {**out, "intent": "review_accepted"}
                ok = engine.resume_run(out["trace_id"], req.query)
                if not ok:
                    return JSONResponse({"error": "run not paused"},
                                        status_code=409)
                return {"intent": "resume", **out}
            return {"intent": "new"}

    @app.post("/runs/{trace_id}/review")
    async def review(trace_id: str, req: ReviewRequest):
        """审阅裁决入口（engine.review_run 幂等：首个生效，后续 409）。

        action 词汇表对前端用 replan（重做语义），engine 侧事件名是
        reject（REVIEW_REJECT→PLANNING）——此处翻译，Task 4 语义不动。
        """
        if not (runs / trace_id).exists():
            return JSONResponse({"error": "no such run"}, status_code=404)
        ok = engine.review_run(
            trace_id, "accept" if req.action == "accept" else "reject",
            req.feedback)
        if not ok:
            return JSONResponse({"error": "run not awaiting review"},
                                status_code=409)
        return {"reviewed": True, "action": req.action}

    @app.get("/runs/{trace_id}/stream")
    async def run_stream(trace_id: str, request: Request):
        run_dir = runs / trace_id
        if not run_dir.exists():
            return JSONResponse({"error": "no such run"}, status_code=404)
        trace = run_dir / "trace.jsonl"

        async def gen():
            pos = int(request.headers.get("last-event-id", 0))
            idle = 0.0
            while True:
                fresh = False
                if trace.exists():
                    lines = trace.read_text(encoding="utf-8").splitlines()
                    done = False
                    for i in range(pos, len(lines)):
                        try:
                            rec = json.loads(lines[i])
                        except json.JSONDecodeError:
                            continue  # 进程中途杀的半行跳过
                        if rec.get("event") == "run_end":
                            yield f"id: {i + 1}\nevent: end\ndata: {lines[i]}\n\n"
                            done = True
                            break
                        yield f"id: {i + 1}\nevent: trace\ndata: {lines[i]}\n\n"
                    if done:
                        return
                    fresh = len(lines) > pos
                    pos = len(lines)
                if fresh:
                    idle = 0.0
                else:
                    idle += 0.3
                    if idle >= STREAM_IDLE_CAP:
                        return  # 5s 无增量关流，重连由 Last-Event-ID 续传兜底
                await asyncio.sleep(0.3)  # 轮询 tail；0.3s 足够打字机平滑

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.get("/runs/{trace_id}/artifacts")
    def run_artifacts(trace_id: str) -> list[dict]:
        """各节点的产物内容：artifacts/ 下的文件 + program 节点的执行结果。"""
        artifacts_dir = runs / trace_id / "artifacts"
        out = []
        if artifacts_dir.exists():
            for f in sorted(artifacts_dir.iterdir()):
                if f.is_file():
                    out.append({"name": f.name,
                                "content": f.read_text(encoding="utf-8")[:20_000]})
        # program 节点（case_executor）的执行结果不在 artifacts/，从 checkpoint 取
        cp = runs / trace_id / "checkpoint.json"
        if cp.exists():
            try:
                node_outputs = json.loads(cp.read_text(encoding="utf-8")).get(
                    "node_outputs", {})
                for node_id, node in node_outputs.items():
                    out.append({"name": f"{node_id}_result.json",
                                "content": json.dumps(
                                    node.get("output_data", {}),
                                    ensure_ascii=False, indent=2)})
            except (json.JSONDecodeError, AttributeError):
                pass
        return out

    @app.post("/eval")
    async def start_eval() -> dict:
        eval_id = f"eval-{uuid.uuid4().hex[:8]}"

        async def _run_eval():
            out = runs / eval_id
            try:
                repo = ensure_repo()
                golden = load_golden()
                reports = {}
                for tag in golden:
                    trace_id = await engine.execute(
                        {"repo": str(repo), "commit": tag}, DEFAULT_PLAN)
                    report = runs / trace_id / "artifacts" / "cr_report.json"
                    reports[tag] = (json.loads(report.read_text())
                                    if report.exists() else {})
                summary = evaluate_report(golden, reports)
            except Exception as e:
                summary = {"status": "failed", "error": str(e)}
            out.mkdir(parents=True, exist_ok=True)
            (out / "summary.json").write_text(
                json.dumps(summary, ensure_ascii=False, indent=2))

        _spawn(_run_eval())
        return {"eval_id": eval_id}

    @app.get("/eval/{eval_id}")
    def eval_result(eval_id: str):
        f = runs / eval_id / "summary.json"
        if not f.exists():
            return JSONResponse({"status": "running"}, status_code=202)
        return json.loads(f.read_text())

    return app


app = create_app()


def main() -> None:
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8100)


if __name__ == "__main__":
    main()
