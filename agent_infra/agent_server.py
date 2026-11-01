"""多 Agent 的 A2A server（独立进程，一进程一 agent，A2A 1.0 / a2a-sdk 1.x）。

`--agent <name>` 加载对应 agent 三件套（build_agent + card + policy）。契约映射：
AgentInput 序列化进 task message；AgentOutput 经终止态 message + artifact 送回；
执行事件经 TaskStatusUpdateEvent(message) 流回 harness。A2A task 记录落盘
runs/<trace_id>/a2a_task.json（本地文件存储）。
"""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import uvicorn
from a2a.helpers import new_task_from_user_message
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import (
    add_a2a_routes_to_fastapi,
    create_agent_card_routes,
    create_jsonrpc_routes,
)
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.server.tasks.task_updater import TaskUpdater
from a2a.types import (
    AgentCard,
    AgentInterface,
    Part,
    TaskState,
)
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from harness.callbacks import _TURN_KEY  # 轮次计数键：与 callbacks 单一来源
from harness.config import runs_root
from harness.contract import OutputContractError, RunContext, parse_output
from harness.policy import DEFAULT_NODE_POLICY, NODE_POLICIES, NodePolicy
from harness.registry import resolve_node
from harness.sandbox.manager import SandboxManager
from harness.trace import Tracer

RUNS = runs_root()  # env AGENT_INFRA_RUNS_DIR 注入，默认 agent_infra/runs（本地持久化）
RPC_URL = "/a2a/jsonrpc"
_AGENTS_DIR = Path(__file__).parent / "agents"

RunAgentFn = Callable[[RunContext, str], Awaitable[str]]


# ---- agent 输出 finalize（parse → output_data + artifact 名）----

def _parse_json(text: str) -> dict:
    """通用：剥 fence + json.loads（planning 等输出 JSON 本体的 agent）。"""
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL)
    data = json.loads(m.group(1).strip() if m else text)
    if not isinstance(data, dict):
        raise OutputContractError("agent output is not a json object")
    return data


def _parse_cr(text: str) -> dict:
    """CR 严格契约（issues/verdict/summary）。"""
    return parse_output(text).output_data


def _parse_script(text: str) -> dict:
    """Testing agent 输出 pytest 脚本（非 JSON，原样收）。"""
    return {"script": text}


def _parse_report(text: str) -> dict:
    """report 契约：summary/verdicts + markdown（markdown 原文落 execution_report.md）。"""
    data = _parse_json(text)
    if not isinstance(data.get("summary"), str) or not data["summary"]:
        raise OutputContractError("report.summary must be a non-empty string")
    if not isinstance(data.get("verdicts"), list):
        raise OutputContractError("report.verdicts must be a list")
    if (not isinstance(data.get("markdown"), str)
            or not data["markdown"].strip()):
        raise OutputContractError("report.markdown must be non-empty")
    data.setdefault("stats", {})
    if not isinstance(data.get("root_causes_n", 0), int):
        raise OutputContractError("report.root_causes_n must be an int")
    return data


def _parse_recall(text: str) -> dict:
    """测试召回契约：recalled/gaps 是召回与缺口清单，recall_stats 记账。"""
    data = _parse_json(text)
    if not isinstance(data.get("recalled"), list):
        raise OutputContractError("recall.recalled must be a list")
    if not isinstance(data.get("gaps"), list):
        raise OutputContractError("recall.gaps must be a list")
    if not isinstance(data.get("recall_stats"), dict):
        raise OutputContractError("recall.recall_stats must be a dict")
    return data


_CASE_KEYS = ("id", "scenario", "action", "src", "linked_risk")


def _parse_case_list(text: str) -> dict:
    """用例清单契约：case_list 是 list（**允许空**——无风险输入的诚实降级，
    与 _parse_recall 的空 recalled/gaps 同惯例）；非空时每条五键齐、
    action 出域与 id 重复都拒。"""
    data = _parse_json(text)
    cases = data.get("case_list")
    if not isinstance(cases, list):
        raise OutputContractError("case_list.case_list must be a list")
    seen: set[str] = set()
    for case in cases:
        if not isinstance(case, dict) or any(k not in case for k in _CASE_KEYS):
            raise OutputContractError(
                f"case_list entries must each contain {_CASE_KEYS}")
        if case["action"] not in ("reuse", "generate"):
            raise OutputContractError(
                f"case_list.action must be reuse|generate, got {case['action']!r}")
        if not str(case["id"]).strip():
            raise OutputContractError("case_list.id must be non-empty")
        if case["id"] in seen:
            raise OutputContractError(f"case_list.id duplicated: {case['id']}")
        seen.add(case["id"])
    return data


def _parse_change_report(text: str) -> dict:
    """变更分析报告契约：summary/markdown 非空 + risk_n/recalled_n/recommended_n
    是 int（计数是下游断言锚点，漂成 str 就静默失真）。"""
    data = _parse_json(text)
    if not isinstance(data.get("summary"), str) or not data["summary"]:
        raise OutputContractError("change_report.summary must be a non-empty string")
    for key in ("risk_n", "recalled_n", "recommended_n"):
        if not isinstance(data.get(key), int):
            raise OutputContractError(f"change_report.{key} must be an int")
    if (not isinstance(data.get("markdown"), str)
            or not data["markdown"].strip()):
        raise OutputContractError("change_report.markdown must be non-empty")
    return data


_DIAGNOSE_KEYS = ("case", "cause", "evidence")


def _parse_diagnose(text: str) -> dict:
    """诊断契约：root_causes 每条含 case/cause/evidence 三键，summary 非空。
    空数组合法（全过/未执行时如实输出空，矩阵 #7——不编造根因）。"""
    data = _parse_json(text)
    causes = data.get("root_causes")
    if not isinstance(causes, list):
        raise OutputContractError("diagnose.root_causes must be a list")
    for cause in causes:
        if not isinstance(cause, dict) or any(k not in cause
                                              for k in _DIAGNOSE_KEYS):
            raise OutputContractError(
                f"diagnose.root_causes entries must each contain {_DIAGNOSE_KEYS}")
    if not isinstance(data.get("summary"), str) or not data["summary"]:
        raise OutputContractError("diagnose.summary must be a non-empty string")
    return data


_FINALIZE: dict[str, tuple[Callable[[str], dict], str]] = {
    "cr_agent": (_parse_cr, "cr_report"),
    "planning_agent": (_parse_json, "plan"),
    "script_agent": (_parse_script, "test_cases"),
    "requirement_agent": (_parse_json, "requirement_brief"),
    "strategy_agent": (_parse_json, "review_strategy"),
    "report_agent": (_parse_report, "execution_report.md"),
    "test_recall_agent": (_parse_recall, "test_recall"),
    "case_agent": (_parse_case_list, "case_list"),
    "change_report_agent": (_parse_change_report, "change_report.md"),
    "diagnose_agent": (_parse_diagnose, "diagnose"),
}


def _make_validator(parse_fn: Callable[[str], dict]) -> Callable[[str], None]:
    """把 agent 的 finalize 契约包成修复轮判定（抛异常 = 格式漂移需修复）。"""
    def validate(text: str) -> None:
        parse_fn(text)
    return validate


@dataclass(frozen=True)
class AgentSpec:
    """一进程一 agent 的加载结果：三件套 + 运行期 url + 输出 finalize。"""
    name: str
    url: str
    build_agent: Callable[[RunContext, SandboxManager, NodePolicy], object]
    policy: NodePolicy
    card_path: Path
    parse: Callable[[str], dict]
    artifact_name: str
    validate: Callable[[str], None] | None = None   # 修复轮判定（None=cr 严格契约）
    repair_prompt: str | None = None                # 修复轮提示（None=cr 专用提示）


def load_agent_by_name(name: str) -> AgentSpec:
    """按名加载 agent（registry 校验 + 动态 import 三件套）。

    未知名或 program 节点抛 ValueError（配置错误，早暴露）。
    """
    try:
        spec = resolve_node(name)
    except KeyError:
        raise ValueError(f"unknown agent: {name}") from None
    if spec.type != "agent":
        raise ValueError(f"{name} is a program node, not an agent")
    from importlib import import_module

    mod = import_module(f"agents.{name}.agent")
    parse_fn, artifact_name = _FINALIZE.get(name, (_parse_json, name))
    # V3：非 cr agent 的修复轮按自身契约判定（planning/testing 一并受益——
    # 此前它们被 cr 契约误审，合法输出也触发无意义的 cr 形状修复轮）
    validate, repair = (None, None) if name == "cr_agent" else (
        _make_validator(parse_fn), _GENERIC_REPAIR)
    return AgentSpec(
        name=name, url=spec.url, build_agent=mod.build_agent,
        policy=NODE_POLICIES.get(name, DEFAULT_NODE_POLICY),
        card_path=_AGENTS_DIR / name / "agent-card.json",
        parse=parse_fn, artifact_name=artifact_name,
        validate=validate, repair_prompt=repair)


def load_agent_card(path: Path, base_url: str) -> AgentCard:
    """AgentCard 身份来自 agent 目录下的 JSON（agent 定义的一部分）；
    server 只负责注入运行时才知道的接口地址。"""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data["supported_interfaces"] = [AgentInterface(
        protocol_binding="JSONRPC", protocol_version="1.0",
        url=f"{base_url}{RPC_URL}")]
    return AgentCard(**data)


def render_prompt(agent_input_json: str) -> str:
    return ("处理以下任务输入，按你的输出契约返回结果：\n"
            + agent_input_json)


_REPAIR_PROMPT = (
    "你上一条最终回复没有包含符合输出契约的 JSON（只有陈述文字）。"
    "现在只输出该 JSON 对象本体（issues/verdict/summary），不要任何解释、"
    "不要 markdown 代码围栏之外的文字。")

# 非 cr 契约 agent 的修复提示（不点名字段——各 agent 契约不同，以各自 prompt 为准）
_GENERIC_REPAIR = (
    "你上一条最终回复没有包含符合输出契约的 JSON（只有陈述文字）。"
    "现在只输出符合你输出契约的 JSON 对象本体，不要任何解释、"
    "不要 markdown 代码围栏之外的文字。")


def _split_parts(parts) -> tuple[str, str]:
    """拆 (答案文本, 思考文本)：thought part 是推理模型的 CoT（ADK 以
    thought=True 标记，通常排在 parts[0]），答案在其余 part。"""
    answer = "".join(p.text for p in parts
                     if getattr(p, "text", None)
                     and not getattr(p, "thought", False))
    thought = "".join(p.text for p in parts
                      if getattr(p, "text", None) and getattr(p, "thought", False))
    return answer, thought


def _sink_deltas(ev, run: RunContext) -> None:
    """非 final 事件的部分文本 → llm_delta（打字机数据源，终值另有 llm_thought 兜底）。"""
    parts = getattr(getattr(ev, "content", None), "parts", None) or []
    for part in parts:
        delta = getattr(part, "text", None)
        if delta:
            run.event_sink("llm_delta", {
                "text": delta, "thought": bool(getattr(part, "thought", False))})


async def _get_or_create_session(runner, session_key: str):
    """ADK session 寻回：同 run 同节点复用（打断 resume 后 agent 上下文还在）。"""
    svc = runner.session_service
    session = await svc.get_session(
        app_name="agent_infra", user_id="harness", session_id=session_key)
    if session is None:
        session = await svc.create_session(
            app_name="agent_infra", user_id="harness", session_id=session_key)
    return session


def make_adk_run(build_agent, policy: NodePolicy, *,
                 validate: Callable[[str], None] | None = None,
                 repair_prompt: str | None = None) -> RunAgentFn:
    """闭包一个 adk 执行函数：按 agent 的 build_agent + policy 跑单次会话。

    manager 经模块级 _MANAGER 注入（build_a2a_app 时设置），与 build_agent
    的 (run, manager, policy) 签名对齐。validate/repair_prompt 缺省 = cr 的
    严格契约路径（历史行为不变）；非 cr agent 由 load_agent_by_name 按自身
    finalize 契约注入（V3：修复轮不得拿 cr 契约审别的 agent 的输出）。
    """
    async def adk_run(run: RunContext, prompt: str) -> str:
        from google.adk.runners import Runner
        from google.genai import types

        agent = build_agent(run, _MANAGER, policy)
        runner = Runner(agent=agent, app_name="agent_infra",
                        session_service=_session_service())
        session = await _get_or_create_session(
            runner, f"{run.trace_id}:{run.node_id or 'main'}")
        # ponytail: 每次 adk_run 重置轮次计数——session 按 trace:node 复用（打断
        # 续聊），但 node_retry 是新执行新预算；不重置则重试从旧计数起步瞬间
        # 撞预算死亡（全链冒烟实测：第 2/3 次尝试 turn=16 起步）。DB 后端必须
        # 走 append_event+state_delta 持久化，直接改 session.state 不落库
        # getattr 守卫：单测的 fake session（SimpleNamespace）可能没有 state
        if (getattr(session, "state", None) or {}).get(_TURN_KEY):
            from google.adk.events import Event, EventActions
            await runner.session_service.append_event(session, Event(
                author="harness",
                actions=EventActions(
                    state_delta={_TURN_KEY: 0})))

        async def _run_once(text: str) -> str:
            final = ""
            async for ev in runner.run_async(
                    user_id="harness", session_id=session.id,
                    new_message=types.Content(role="user",
                                              parts=[types.Part(text=text)])):
                if not ev.is_final_response():
                    _sink_deltas(ev, run)
                if ev.is_final_response() and ev.content and ev.content.parts:
                    final, thought = _split_parts(ev.content.parts)
                    if thought:
                        run.event_sink("llm_thought", {"text": thought[:1500],
                                                       "full_len": len(thought)})
            return final

        final = await _run_once(prompt)
        # 契约修复轮：模型审对了但输出格式漂移（GLM 常见：中文陈述代替 JSON）
        # ——同一 session 追一轮强约束，省一次全量重审。只修格式，不重试审查。
        # 判定按 agent 自己的契约（V3）；json 解析错是 ValueError 子类，一并触发
        check = validate or parse_output
        try:
            check(final)
        except (OutputContractError, ValueError):
            run.event_sink("contract_repair", {"reason": "format drift"})
            final = await _run_once(repair_prompt or _REPAIR_PROMPT)
        return final

    return adk_run


def _user_text(context) -> str:
    """兼容地取 user message 文本（RequestContext.get_user_input 为同步方法）。"""
    get_input = getattr(context, "get_user_input", None)
    if get_input:
        return get_input()
    msg = getattr(context, "message", None)
    if msg is not None and msg.parts:
        return "".join(p.text for p in msg.parts if getattr(p, "text", None))
    raise ValueError("no user message in request context")


class A2AAgentExecutor(AgentExecutor):
    def __init__(self, runs_root: Path, manager: SandboxManager,
                 spec: AgentSpec, run_agent: RunAgentFn | None = None) -> None:
        self._runs_root = Path(runs_root)
        self._manager = manager
        self._spec = spec
        self._run_agent = run_agent or make_adk_run(
            spec.build_agent, spec.policy,
            validate=spec.validate, repair_prompt=spec.repair_prompt)

    async def _run_capped(self, run: RunContext, agent_input: dict,
                          trace_id: str, hard_cap: float) -> str:
        """跑 agent 会话，hard cap 兜底 engine crash。

        等人期间（HITL pending）到期即重置上限：无超时设计（§3.2）；
        无人接且到期才 raise，孤儿任务自行终止落 failed。
        """
        from harness.hitl import REGISTRY
        deadline = asyncio.get_running_loop().time() + hard_cap
        inner = asyncio.ensure_future(
            self._run_agent(run, render_prompt(
                json.dumps(agent_input, ensure_ascii=False))))
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                inner.cancel()
                raise TimeoutError
            try:
                return await asyncio.wait_for(asyncio.shield(inner), remaining)
            except asyncio.CancelledError:
                inner.cancel()  # tasks/cancel：会话一并终止，不留孤儿
                raise
            except TimeoutError:
                if inner.done():
                    return inner.result()
                if REGISTRY.pending_for(trace_id):
                    deadline = asyncio.get_running_loop().time() + hard_cap
                    continue
                raise

    async def execute(self, context, event_queue) -> None:
        # A2A 1.0：Task 生命周期流——先入队初始 Task
        user_message = context.message  # proto Message
        task = new_task_from_user_message(user_message)
        await event_queue.enqueue_event(task)
        updater = TaskUpdater(event_queue, task.id, task.context_id)
        await updater.start_work()

        agent_input = json.loads(_user_text(context))
        trace_id = agent_input["run_id"]
        payload = agent_input["input_data"]

        q: asyncio.Queue = asyncio.Queue()

        def sink(event: str, extra: dict) -> None:
            q.put_nowait({"event": event, **extra})

        run = RunContext(trace_id=trace_id, repo_path=payload["repo"],
                         commit=payload["commit"],
                         artifacts_dir=str(self._runs_root / trace_id / "artifacts"),
                         node_id=agent_input.get("node_id", ""),
                         attempt=agent_input.get("attempt", 1),
                         event_sink=sink)
        drain = asyncio.create_task(self._drain(q, updater))
        flushed = False

        async def _flush() -> None:
            # 终态前先停 drain 并清空队列，避免 WORKING 事件落在 COMPLETED/FAILED 之后
            nonlocal flushed
            if flushed:
                return
            flushed = True
            await q.put(None)
            await drain

        try:
            # crash 兜底：engine 侧 wait_for 是权威预算；这里再加一道 server
            # 侧硬上限（policy timeout + 余量），engine 进程死掉时孤儿任务
            # 也能自行终止落 failed，不悬挂。CancelledError（A2A tasks/cancel）
            # 是 BaseException 子类，不会被下面的 except 捕获，走 finally 收尾
            hard_cap = self._spec.policy.timeout_s + 60
            text = await self._run_capped(run, agent_input, trace_id, hard_cap)
            output_data = self._spec.parse(text)
            artifact_dir = self._runs_root / trace_id / "artifacts"
            artifact_dir.mkdir(parents=True, exist_ok=True)
            if self._spec.artifact_name.endswith(".md"):
                # markdown 产物（report）：契约里的 markdown 字段原文写盘
                artifact_file = artifact_dir / self._spec.artifact_name
                artifact_file.write_text(
                    str(output_data.get("markdown", "")), encoding="utf-8")
            else:
                artifact_file = artifact_dir / f"{self._spec.artifact_name}.json"
                artifact_file.write_text(
                    json.dumps(output_data, ensure_ascii=False, indent=2),
                    encoding="utf-8")
            artifacts = [{"artifact_id": f"{self._spec.artifact_name}-{trace_id}",
                          "type": self._spec.artifact_name,
                          "uri": str(artifact_file)}]
            result_json = json.dumps(
                {"output_data": output_data, "artifact_url": str(artifact_file),
                 "status": "ok", "artifacts": artifacts}, ensure_ascii=False)
            (self._runs_root / trace_id / "a2a_task.json").write_text(json.dumps({
                "context_id": trace_id, "status": "completed",
                "artifact_url": str(artifact_file)}, ensure_ascii=False),
                encoding="utf-8")
            await _flush()
            await updater.add_artifact(
                parts=[Part(text=result_json)], name=self._spec.artifact_name)
            await updater.complete(
                message=updater.new_agent_message([Part(text=result_json)]))
        except OutputContractError as e:
            await _flush()
            await updater.failed(message=updater.new_agent_message(
                [Part(text=f"contract violation: {e}")]))
        except Exception as e:
            await _flush()
            await updater.failed(message=updater.new_agent_message(
                [Part(text=f"{self._spec.name} failed: {e}")]))
        finally:
            await _flush()

    async def cancel(self, context, event_queue) -> None:
        # A2A 契约（DefaultRequestHandler.on_cancel_task）：executor 负责把
        # task 推到 CANCELED 终态；执行体由框架对 execute() 的 producer task
        # cancel()（CancelledError 在 await 点抛出，execute 走 finally 收尾）
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.update_status(TaskState.TASK_STATE_CANCELED)

    async def _drain(self, q: asyncio.Queue, updater: TaskUpdater) -> None:
        while True:
            item = await q.get()
            if item is None:
                return
            # 事件流失败不影响执行
            with contextlib.suppress(Exception):
                await updater.update_status(
                    TaskState.TASK_STATE_WORKING,
                    message=updater.new_agent_message([Part(
                        text="agent_event:" + json.dumps(item, ensure_ascii=False))]))


_MANAGER: SandboxManager | None = None
_SESSION_SERVICE = None


def _session_service():
    """进程级单例：一进程一 AsyncEngine 一池（预研 §3.1 实证——每次新建不
    dispose，13/50 aiosqlite 连接 GC 不可达，长活进程慢泄漏）。"""
    global _SESSION_SERVICE  # noqa: PLW0603 —— 惰性单例，测试经 _reset 隔离
    if _SESSION_SERVICE is None:
        from google.adk.sessions import DatabaseSessionService

        _SESSION_SERVICE = DatabaseSessionService(
            # ADK 走 sqlalchemy async：必须显式 aiosqlite 驱动，否则构造即抛
            db_url=f"sqlite+aiosqlite:///{RUNS / 'adk_sessions.db'}")
    return _SESSION_SERVICE


def _reset_session_service() -> None:
    """测试钩子：单例指向模块级 RUNS，测试换 tmp db 时先 reset 再 monkeypatch。"""
    global _SESSION_SERVICE  # noqa: PLW0603 —— 同上，测试钩子
    _SESSION_SERVICE = None


TTL_SWEEP_INTERVAL_S = 60.0


async def _ttl_sweeper(manager: SandboxManager, runs_root: Path,
                       timeout_s: float) -> None:
    """防线层2 TTL 清扫：idle > 2× 节点硬上限的 session 兜底回收——覆盖
    engine 崩溃 / shutdown HTTP 失败的孤儿（预研 §3.1 层2）。"""
    ttl_s = 2 * timeout_s
    while True:
        await asyncio.sleep(TTL_SWEEP_INTERVAL_S)
        for rid in manager.sweep(ttl_s=ttl_s):
            Tracer(runs_root, rid).emit("sandbox_reclaim", layer="ttl")


def build_a2a_app(runs_root: Path, manager: SandboxManager,
                  spec: AgentSpec, run_agent: RunAgentFn | None = None) -> FastAPI:
    global _MANAGER  # noqa: PLW0603 —— adk_run 惰性取 manager，模块级注入是最小方案
    _MANAGER = manager
    runs_root = Path(runs_root)
    runs_root.mkdir(parents=True, exist_ok=True)

    card = load_agent_card(spec.card_path, spec.url)
    handler = DefaultRequestHandler(
        agent_executor=A2AAgentExecutor(runs_root, manager, spec, run_agent),
        task_store=InMemoryTaskStore(),  # ponytail: task 状态已由 executor 落盘
        agent_card=card,
    )
    @contextlib.asynccontextmanager
    async def lifespan(_app: FastAPI):
        # 防线层3 boot sweep：启动自愈——终态/无 checkpoint 的残留沙箱回收
        # （prune 清不掉「目录还在」的死条目，预研 §3.1 层3）；幂等可重入。
        # 回收/打点失败不阻断 server 启动（与 sweep 循环「回收失败不阻断」同语义）
        try:
            for rid in manager.boot_sweep():
                Tracer(runs_root, rid).emit("sandbox_reclaim", layer="boot")
        except Exception:
            pass
        sweeper = asyncio.create_task(_ttl_sweeper(
            manager, runs_root, spec.policy.timeout_s))
        try:
            yield
        finally:
            sweeper.cancel()

    app = FastAPI(title=f"{spec.name} a2a server", lifespan=lifespan)
    add_a2a_routes_to_fastapi(
        app,
        agent_card_routes=create_agent_card_routes(card),
        jsonrpc_routes=create_jsonrpc_routes(handler, rpc_url=RPC_URL),
    )

    @app.post("/admin/sandboxes/{trace_id}/shutdown")
    async def shutdown(trace_id: str) -> JSONResponse:
        manager.shutdown(trace_id)
        return JSONResponse({"shutdown": trace_id})

    # HITL side 路由：app 收 /runs/{id}/hitl 后转发到这里唤醒 agent 的等待
    from harness.hitl import REGISTRY as _HITL

    @app.post("/internal/hitl/{trace_id}")
    async def hitl_answer(trace_id: str, body: dict) -> JSONResponse:
        # {"text": null} 归一为 ""：resolve 里 .strip() 不吃 None
        ok = _HITL.resolve(trace_id, body.get("text") or "")
        return JSONResponse({"resolved": ok}, status_code=200 if ok else 404)

    return app


def main() -> None:
    from harness.sandbox.worktree import WorktreeProvider

    parser = argparse.ArgumentParser(description="agent_infra A2A agent server")
    parser.add_argument("--agent", default="cr_agent",
                        help="agent name in registry (cr_agent/diagnose_agent/...)")
    args = parser.parse_args()

    spec = load_agent_by_name(args.agent)
    manager = SandboxManager(
        WorktreeProvider(allowed_cmds=spec.policy.allowed_cmds), RUNS)
    app = build_a2a_app(RUNS, manager, spec)
    port = int(spec.url.rsplit(":", 1)[1])
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
