"""L 层：HarnessEngine 调度循环（A2A client 权威，状态机驱动）。

harness 决定"何时回收"（决策），agent server 的 sandbox provider 决定"怎么回收"。
多 agent 编排：Planning agent 产出 ExecutionPlan → 按 plan 拓扑序调度——
Agent 节点走 A2A（按 registry 查 url），Program 节点走本地 handler。
链式数据流：上游 AgentOutput.artifacts → 下游 AgentInput.artifact_refs。
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import time
import uuid
from pathlib import Path

import httpx

from harness.checkpoint import (
    Checkpoint,
    idempotency_key,
    load_checkpoint,
    save_checkpoint,
)
from harness.contract import (
    AgentInput,
    AgentOutput,
    ExecutionPlan,
    parse_plan,
    parse_result,
)
from harness.memory import MemoryStore, NoopMemory, RecallSpec
from harness.policy import DEFAULT_NODE_POLICY, NODE_POLICIES, NodePolicy
from harness.programs import PROGRAM_HANDLERS
from harness.registry import AGENT_REGISTRY, NodeSpec, resolve_node
from harness.state import HarnessState, StateMachine
from harness.trace import Tracer

DEFAULT_NODE_TIMEOUT_S = 600

UPSTREAM_MAX_CHARS = 500   # 每节点语义结论预算（设计 §2：契约约束 + 超限截断）


def _clip_upstream(data: object) -> dict | None:
    """上游结论守卫：非 dict/空 dict → None（无语义跳过）；
    JSON 超 500 字 → 头部截断 + 诚实标注（矩阵 #1）。"""
    if not isinstance(data, dict) or not data:
        return None
    text = json.dumps(data, ensure_ascii=False)
    if len(text) <= UPSTREAM_MAX_CHARS:
        return data
    return {"_truncated": True, "head": text[:UPSTREAM_MAX_CHARS]}


def _build_upstream(node_outputs: dict, completed: list[str],
                    by_id: dict[str, dict]) -> tuple[dict, list[str], int]:
    """组装 AgentInput.upstream = {registry 名: 语义结论}。

    键用 registry 名（跨 plan 稳定，prompt 可硬编码引用）。坏条目（条目非
    dict / output_data 非 dict）跳过并计数，由调用方发 upstream_corrupt
    （矩阵 #4）；空结论静默跳过（矩阵 #2 的宽容面，不计数）。
    """
    upstream: dict = {}
    nodes: list[str] = []
    corrupt = 0
    for nid in completed:
        entry = node_outputs.get(nid)
        if entry is None:  # 缺条目（矩阵 #2 宽容面）：未跑/失败，静默跳过不计数
            continue
        if not isinstance(entry, dict):
            corrupt += 1
            continue
        data = entry.get("output_data")
        if data is not None and not isinstance(data, dict):
            corrupt += 1
            continue
        clipped = _clip_upstream(data)
        if clipped is None:
            continue
        node = by_id.get(nid) or {}
        ref = node.get("agent") or node.get("program") or nid
        upstream[ref] = clipped
        nodes.append(ref)
    return upstream, nodes, corrupt


# 默认 plan：单 CR（一期行为，plan 显式给出即跳过 planning 阶段）
DEFAULT_PLAN = ExecutionPlan(
    plan_id="default",
    nodes=[{"id": "cr", "agent": "cr_agent"}],
    edges=[],
)


class _NodeBudget:
    """节点超时预算：HITL 心跳到达时外推（等人不耗预算，设计 §3.2）。"""

    def __init__(self, timeout_s: float) -> None:
        self.deadline = asyncio.get_running_loop().time() + timeout_s

    def extend(self, secs: float = 180.0) -> None:
        self.deadline = max(self.deadline,
                            asyncio.get_running_loop().time() + secs)


@dataclasses.dataclass
class _RunHandle:
    """进行中 run 的打断句柄：pause 打断 body，resume 唤醒续跑。"""

    trace_id: str
    pause_requested: bool = False
    resume_event: asyncio.Event | None = None
    feedback: str = ""
    body_task: asyncio.Task | None = None
    current_node: str | None = None
    node_urls: set[str] = dataclasses.field(default_factory=set)  # 参与节点 url（回收广播用）


def _topo_order(nodes: list[dict], edges: list[list[str]]) -> list[str]:
    """节点按依赖边的拓扑序执行；有环抛 ValueError。"""
    ids = [n["id"] for n in nodes]
    indeg: dict[str, int] = {i: 0 for i in ids}
    adj: dict[str, list[str]] = {i: [] for i in ids}
    for a, b in edges:
        if a not in adj or b not in indeg:
            raise ValueError(f"edge references unknown node: {a} -> {b}")
        adj[a].append(b)
        indeg[b] += 1
    ready = [i for i in ids if indeg[i] == 0]
    order: list[str] = []
    while ready:
        n = ready.pop()
        order.append(n)
        for m in adj[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                ready.append(m)
    if len(order) != len(ids):
        raise ValueError("plan has a cycle")
    return order


class HarnessEngine:
    def __init__(self, agent_base_url: str, runs_root: Path,
                 memory: MemoryStore | None = None,
                 httpx_client: httpx.AsyncClient | None = None,
                 agent_urls: dict[str, str] | None = None) -> None:
        # agent_base_url 为单 URL 覆盖（一期单 agent 部署 / 测试）；为空时按
        # registry 每节点查 url（多 agent 一进程一端口）。agent_urls 按 node 覆盖
        # （测试起多 fake server 时用）。
        self.base_url = agent_base_url.rstrip("/") if agent_base_url else None
        self.runs_root = Path(runs_root)
        self.memory = memory or NoopMemory()
        self._http = httpx_client
        self._url_overrides = agent_urls or {}
        self.node_timeout_s = DEFAULT_NODE_TIMEOUT_S
        self._active_boxes: dict[str, dict] = {}  # run_id → {url, task_id_box}（pause 用）
        self._runs: dict[str, _RunHandle] = {}    # trace_id → 打断句柄（pause/resume 用）

    def _url_for(self, node_id: str) -> str:
        if node_id in self._url_overrides:
            return self._url_overrides[node_id]
        if self.base_url:
            return self.base_url
        return resolve_node(node_id).url

    def _primary_url(self) -> str:
        """沙箱回收走主 agent（cr）的 server；覆盖优先。"""
        return self._url_for("cr_agent")

    def node_urls(self) -> list[str]:
        """全量 agent url（去重）：app 转发 HITL 答案时广播用。"""
        urls = {spec["url"] for spec in AGENT_REGISTRY.values()
                if spec.get("url")}
        urls.update(self._url_overrides.values())
        return sorted(urls)

    def _client(self) -> tuple[httpx.AsyncClient, bool]:
        """(client, should_close)——trust_env=False 同 _send（不打系统代理）"""
        if self._http:
            return self._http, False
        return httpx.AsyncClient(trust_env=False), True

    def _step(self, sm: StateMachine, trigger: str, tracer: Tracer) -> HarnessState:
        before = sm.state
        sm.transition(trigger)
        tracer.emit("state_transition", from_=before.value,
                    to=sm.state.value, trigger=trigger)
        return sm.state

    async def execute(self, payload: dict,
                      plan: ExecutionPlan | None = None) -> str:
        trace_id = uuid.uuid4().hex
        await self.execute_for(trace_id, payload, plan)
        return trace_id

    async def execute_for(self, trace_id: str, payload: dict,
                          plan: ExecutionPlan | None = None) -> str:
        """以调用方指定的 trace_id 执行（web 层先建 id 再后台跑）。

        plan 为 None 时走 planning 阶段（调 planning agent 生成 plan）；
        显式给出则直接执行（DEFAULT_PLAN 单 CR 即一期行为）。
        """
        tracer = Tracer(self.runs_root, trace_id)
        tracer.emit("run_start", payload=payload)
        sm = StateMachine()
        self._step(sm, "SUBMIT_TASK", tracer)  # IDLE → PLANNING
        context_id = payload.get("context_id") or trace_id
        handle = _RunHandle(trace_id)
        self._runs[trace_id] = handle
        last_output: AgentOutput | None = None
        try:
            if plan is None:
                plan = await self._plan(trace_id, payload, tracer, context_id)
            if not plan.nodes:
                raise ValueError("empty plan")
            self._step(sm, "PLAN_READY", tracer)  # PLANNING → EXECUTING
            # 打点①规划完成：沿用磁盘已有进度（execute_for 复用 checkpoint 的
            # 接缝）；损坏 checkpoint 视为空，不挡新 run
            try:
                prev = load_checkpoint(self.runs_root, trace_id) or {}
            except json.JSONDecodeError:
                prev = {}
            self._save_cp(tracer, trace_id, "executing",
                          completed_nodes=prev.get("completed_nodes"),
                          node_outputs=prev.get("node_outputs"),
                          context_id=context_id)
            while True:  # 暂停循环：body 被 pause 打断 → 落 checkpoint 挂起等 resume
                body = asyncio.create_task(
                    self._execute_plan(trace_id, payload, plan, sm,
                                       tracer, context_id=context_id))
                handle.body_task = body
                try:
                    last_output = await body
                    self._step(sm, "ALL_STEPS_DONE", tracer)  # → COMPLETED
                    break
                except asyncio.CancelledError:
                    if not handle.pause_requested:
                        raise    # 真取消（进程关闭等），不是用户打断
                    await self._park_for_resume(handle, sm, tracer, trace_id,
                                                context_id)
                    # 始终覆写：resume 带意见则注入，否则置 None——否则上一次
                    # 注入会残留在 payload 里泄漏给后续节点和后续空 resume
                    payload = {**payload, "hitl_feedback": (
                        {"text": handle.feedback} if handle.feedback else None)}
                    self._step(sm, "RESUME", tracer)  # PAUSED → EXECUTING
                    tracer.emit("run_resumed", node_id=handle.current_node)
        except Exception:
            self._step(sm, "ERROR", tracer)  # → FAILED
            self._save_cp(tracer, trace_id, "failed",
                          context_id=context_id)  # 打点④失败
            raise
        finally:
            handle = self._runs.pop(trace_id, None)
            await self._shutdown_sandboxes(
                trace_id, tracer,
                urls=handle.node_urls if handle else None)
            try:
                self.memory.record(trace_id, last_output, context_id=context_id,
                                   commit=payload.get("commit", ""))
            except Exception as exc:  # memory 失败不阻断 run（设计 §9）
                tracer.emit("memory_failed", phase="record", error=str(exc))
            tracer.emit("run_end", status=(
                last_output.status if last_output and last_output.status == "ok"
                else "failed"))
        return trace_id

    async def _park_for_resume(self, handle: _RunHandle, sm: StateMachine,
                               tracer: Tracer, trace_id: str,
                               context_id: str) -> None:
        """落 paused checkpoint 后挂起等 resume（body 已退出，无并发写盘）。"""
        handle.pause_requested = False
        cp = load_checkpoint(self.runs_root, trace_id) or {}  # 磁盘打点③是权威
        self._step(sm, "NEED_HUMAN_INPUT", tracer)  # EXECUTING → PAUSED
        self._save_cp(tracer, trace_id, "paused",
                      current_node=handle.current_node,
                      completed_nodes=cp.get("completed_nodes", []),
                      node_outputs=cp.get("node_outputs", {}),
                      context_id=context_id)
        tracer.emit("run_paused", node_id=handle.current_node)
        if handle.resume_event is None:  # pause_run 已预建则复用
            handle.resume_event = asyncio.Event()
        await handle.resume_event.wait()
        handle.resume_event = None

    async def _plan(self, trace_id: str, payload: dict,
                    tracer: Tracer, context_id: str) -> ExecutionPlan:
        spec = resolve_node("planning_agent")
        policy = NODE_POLICIES.get("planning_agent", DEFAULT_NODE_POLICY)
        agent_input = AgentInput(run_id=trace_id, node_id="planning_agent",
                                 input_data=payload, context_id=context_id)
        output = await self._run_node(
            spec, agent_input, policy,
            min(policy.timeout_s, self.node_timeout_s), tracer)
        if output.status != "ok":
            raise RuntimeError(f"planning failed: {output.status}")
        plan = parse_plan(json.dumps(output.output_data, ensure_ascii=False))
        # nodes 携带 registry 引用（agent/program）：前端 DAG 按 registry id
        # 高亮/着色，plan 内部 id（cr/execute）与之不同构
        tracer.emit("plan_ready", plan_id=plan.plan_id,
                    nodes=[{"id": n["id"],
                            "agent": n.get("agent") or n.get("program")}
                           for n in plan.nodes])
        return plan

    async def _execute_plan(self, trace_id: str, payload: dict,
                            plan: ExecutionPlan, sm: StateMachine,
                            tracer: Tracer, *, context_id: str) -> AgentOutput:
        # 断点续跑：从 checkpoint 载入进度，已完成节点跳过（idempotency 语义）
        completed, node_outputs = self._completed_from_disk(
            self.runs_root, trace_id, plan)
        by_id = {n["id"]: n for n in plan.nodes}
        order = _topo_order(plan.nodes, plan.edges)
        artifact_refs: list = []
        for nid in order:  # 按拓扑序重建已完成节点的产物引用链（下游要用）
            entry = node_outputs.get(nid)
            if nid in completed and isinstance(entry, dict):  # 坏条目守卫（矩阵 #4）
                artifact_refs.extend(entry.get("artifacts", []))
        last_output = AgentOutput({}, "", "ok")
        for nid in order:
            node = by_id[nid]
            ref = node.get("agent") or node.get("program")
            if nid in completed:
                continue  # 断点续跑：已完成节点跳过（idempotency 语义）
            handle = self._runs.get(trace_id)
            if handle:
                handle.current_node = nid
            spec = resolve_node(ref)  # 未知节点 KeyError = 配置错误
            # 打点前组装 upstream：node_start payload 持久化「这个节点看到了
            # 什么」（已截断）+ agent 引用（七期离线打分节点归属的地基）。
            # program 节点不消费 upstream，如实记空
            upstream: dict = {}
            upstream_nodes: list[str] = []
            corrupt = 0
            if spec.type != "program":
                upstream, upstream_nodes, corrupt = _build_upstream(
                    node_outputs, completed, by_id)
            tracer.emit("node_start", node_id=nid, agent=ref, upstream=upstream)
            self._save_cp(tracer, trace_id, "executing", current_node=nid,
                          completed_nodes=completed, node_outputs=node_outputs,
                          context_id=context_id)  # 打点②执行前
            if spec.type == "program":
                self._step(sm, "EXECUTE_PROGRAM", tracer)
                output = await self._run_program(spec, trace_id, artifact_refs, tracer)
            else:
                self._step(sm, "EXECUTE_AGENT", tracer)
                policy = NODE_POLICIES.get(ref, DEFAULT_NODE_POLICY)
                ctx: list = []
                if policy.memory_enabled:  # recall 按 policy 门控
                    try:
                        ctx = self.memory.recall(RecallSpec(
                            node_id=ref, payload=payload, context_id=context_id,
                            kinds=policy.memory_kinds))
                    except Exception as exc:  # memory 失败不阻断 run（设计 §9）
                        tracer.emit("memory_failed", phase="recall",
                                    error=str(exc))
                        ctx = []
                # 上游语义结论注入（设计 §2）：计算已在 node_start 打点前完成
                if corrupt:  # 矩阵 #4：坏条目跳过 + 计数事件（不阻断）
                    tracer.emit("upstream_corrupt", node_id=nid, skipped=corrupt)
                agent_input = AgentInput(
                    run_id=trace_id, node_id=ref, input_data=payload,
                    context_id=context_id, artifact_refs=list(artifact_refs),
                    history=list(ctx),
                    hitl_feedback=payload.get("hitl_feedback"),
                    upstream=upstream)
                output = await self._run_node(
                    spec, agent_input, policy,
                    min(policy.timeout_s, self.node_timeout_s), tracer)
            # 事件平面（设计 §2）：注入量/截断走 node_end payload，零新事件类型
            tracer.emit("node_end", node_id=nid, status=output.status,
                        upstream_nodes=list(upstream_nodes),
                        upstream_truncated=any(
                            isinstance(v, dict) and v.get("_truncated")
                            for v in upstream.values()))
            artifact_refs.extend(output.artifacts)
            completed.append(nid)
            node_outputs[nid] = {
                "status": output.status, "output_data": output.output_data,
                "artifacts": [{"artifact_id": a.get("artifact_id"),
                               "type": a.get("type"), "uri": a.get("uri")}
                              for a in output.artifacts]}  # 恢复时重建引用链用
            self._save_cp(tracer, trace_id, "executing", current_node=nid,
                          completed_nodes=completed, node_outputs=node_outputs,
                          context_id=context_id)  # 打点③完成
            last_output = output
            if output.status != "ok":  # 下游依赖上游产出，非 ok 即短路
                break
        return last_output

    def _save_cp(self, tracer: Tracer, run_id: str, harness_state: str, *,
                 current_node: str | None = None,
                 completed_nodes: list[str] | None = None,
                 node_outputs: dict | None = None,
                 context_id: str | None = None) -> None:
        cp = Checkpoint(run_id=run_id, context_id=context_id or run_id,
                        current_node=current_node, harness_state=harness_state,
                        completed_nodes=completed_nodes or [],
                        node_outputs=node_outputs or {})
        save_checkpoint(self.runs_root, run_id, dataclasses.asdict(cp))
        tracer.emit("checkpoint", state=harness_state, current_node=current_node)

    @staticmethod
    def _completed_from_disk(run_root: Path, trace_id: str,
                             plan: ExecutionPlan) -> tuple[list[str], dict]:
        """断点进度源：checkpoint 优先；损坏/缺失则从 trace.jsonl 的 node_end(ok)
        推断（产物即进度），推断结果写回新 checkpoint 自愈（设计 §3.3）。"""
        try:
            cp = load_checkpoint(run_root, trace_id)
        except json.JSONDecodeError:
            cp = None
        if cp and cp.get("completed_nodes"):
            # checkpoint 可能来自旧 plan：按当前 plan 节点 id 过滤（与下方
            # 推断分支一致），陈旧 id 不得泄入续跑的 upstream/artifact 链
            ids = {n["id"] for n in plan.nodes}
            return ([nid for nid in cp["completed_nodes"] if nid in ids],
                    {k: v for k, v in cp.get("node_outputs", {}).items()
                     if k in ids})
        completed: list[str] = []
        outputs: dict = {}
        f = run_root / trace_id / "trace.jsonl"
        if f.exists():
            for line in f.read_text(encoding="utf-8").splitlines():
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if (rec.get("event") == "node_end"
                        and rec.get("payload", {}).get("status") == "ok"):
                    nid = rec.get("node_id")
                    if nid and any(n["id"] == nid for n in plan.nodes):
                        completed.append(nid)
                        # trace 只存摘要反解必失真：恢复节点降级标注
                        # {recovered: true}（设计 §3.2），语义结论以 artifact 兜底
                        if not outputs.get(nid):
                            outputs[nid] = {"output_data": {"recovered": True}}
        if completed:
            save_checkpoint(run_root, trace_id, {
                "run_id": trace_id, "context_id": trace_id,
                "current_node": None, "harness_state": "executing",
                "completed_nodes": completed, "node_outputs": outputs,
                "version": 1, "created_at": time.time()})
        return completed, outputs

    async def pause_run(self, trace_id: str) -> bool:
        """用户打断：取消 body + 通知 server 取消当前 A2A task（沙箱保留）。"""
        handle = self._runs.get(trace_id)
        if not handle or handle.body_task is None or handle.body_task.done():
            return False
        act = self._active_boxes.get(trace_id)
        if act:
            await self._cancel_task(act["url"], act["box"],
                                    Tracer(self.runs_root, trace_id))
        # 竞态窗口：上面的 HTTP 往返期间 body 可能推进到下一节点（entry 已被
        # _run_node 替换）或整体完成 —— 重读 entry 取消"当前" task 而非快照旧值；
        # body 已完成则如实返回未暂停（不设 pause_requested/resume_event 簿记）
        cur = self._active_boxes.get(trace_id)
        if cur and cur is not act:
            await self._cancel_task(cur["url"], cur["box"],
                                    Tracer(self.runs_root, trace_id))
        if handle.body_task.done():
            return False
        handle.pause_requested = True
        if handle.resume_event is None:  # 先建事件再 cancel：resume 可立刻跟上
            handle.resume_event = asyncio.Event()
        handle.body_task.cancel()
        return True

    def resume_run(self, trace_id: str, text: str = "") -> bool:
        handle = self._runs.get(trace_id)
        # 已 set 未被引擎消费的 resume 拒绝覆写 feedback（双窗口竞态：窗口 B
        # 的第二次 resume 会丢掉窗口 A 的意见——预研 §四层二的一行守卫）
        if not handle or handle.resume_event is None or handle.resume_event.is_set():
            return False
        handle.feedback = text
        handle.resume_event.set()
        return True

    def paused_runs(self, context_id: str) -> list[dict]:
        """会话内挂起任务：内存 registry + 磁盘 checkpoint 扫描合并（跨进程存活）。

        # ponytail: 不按 context_id 服务端过滤——摘要带 context_id，调用方自行筛；
        # run 量大时改 checkpoint.json 文件名/索引目录，免全目录扫描
        """
        out = []
        seen: set[str] = set()
        for tid, h in self._runs.items():
            if h.resume_event is not None:
                out.append({"trace_id": tid, "current_node": h.current_node})
                seen.add(tid)
        root = self.runs_root
        if not root.exists():
            return out
        for run_dir in sorted(root.iterdir()):  # 复用 recover_interrupted 扫描模式
            if not run_dir.is_dir() or run_dir.name in seen:
                continue
            try:
                cp = load_checkpoint(root, run_dir.name)
            except json.JSONDecodeError:  # 损坏 checkpoint 不挡扫描
                continue
            if cp and cp.get("harness_state") == "paused":
                out.append({"trace_id": run_dir.name,
                            "current_node": cp.get("current_node"),
                            "context_id": cp.get("context_id")})
        return out

    async def _run_program(self, spec: NodeSpec, trace_id: str,
                           artifact_refs: list, tracer: Tracer) -> AgentOutput:
        handler = PROGRAM_HANDLERS.get(spec.handler)
        if handler is None:
            raise ValueError(f"no program handler: {spec.handler}")
        result = handler(self.runs_root, trace_id, artifact_refs)
        if asyncio.iscoroutine(result):
            result = await result
        return AgentOutput(output_data=result, artifact_url="", status="ok",
                           artifacts=result.get("artifacts", []))

    async def _run_node(self, spec: NodeSpec, agent_input: AgentInput,
                        policy: NodePolicy, timeout_s: int,
                        tracer: Tracer) -> AgentOutput:
        url = self._url_for(spec.node_id)
        handle = self._runs.get(agent_input.run_id)
        if handle is not None:
            handle.node_urls.add(url)  # 登记：finally 回收广播到全部参与节点
        task_id_box: dict = {}  # _send 从流里捕获 server 侧 task_id
        self._active_boxes[agent_input.run_id] = {"url": url, "box": task_id_box}
        budget = _NodeBudget(timeout_s)
        try:
            for attempt in range(1, policy.max_attempts + 1):
                # 幂等键随 task 下发：重试不重复副作用；attempt 随行——
                # agent 侧工具首调用前据此 reset 沙箱（矩阵 #16）
                agent_input.idempotency_key = idempotency_key(
                    agent_input.run_id, agent_input.node_id, attempt)
                agent_input.attempt = attempt
                try:
                    send_task = asyncio.create_task(
                        self._send(url, agent_input, tracer, task_id_box,
                                   budget=budget))
                    while True:
                        remaining = budget.deadline - asyncio.get_running_loop().time()
                        if remaining <= 0:
                            send_task.cancel()
                            raise TimeoutError
                        try:
                            return await asyncio.wait_for(
                                asyncio.shield(send_task), remaining)
                        except TimeoutError:
                            if send_task.done():
                                return send_task.result()
                            continue  # deadline 被 HITL 心跳外推 → 继续等
                except TimeoutError:
                    # 两端 cover：engine 放弃等待时通知 server 取消执行，
                    # 不留孤儿任务（server 侧另有 hard cap 兜底 engine crash）
                    await self._cancel_task(url, task_id_box, tracer)
                    tracer.emit("node_timeout", attempt=attempt)
                    return AgentOutput({}, "", "timeout")
                except asyncio.CancelledError:
                    # shield 挡住了取消向 send_task 的传播：pause/进程关闭时
                    # 主动取消本地流读取，不留孤儿任务
                    send_task.cancel()
                    raise
                except Exception as e:
                    tracer.emit("node_retry", attempt=attempt, error=str(e))
                    if attempt < policy.max_attempts:
                        await asyncio.sleep(policy.backoff_s * (2 ** (attempt - 1)))
            await self._cancel_task(url, task_id_box, tracer)
            return AgentOutput({}, "", "failed")
        finally:
            self._active_boxes.pop(agent_input.run_id, None)

    async def _send(self, node_url: str, agent_input: AgentInput, tracer: Tracer,
                    task_id_box: dict | None = None,
                    budget: _NodeBudget | None = None) -> AgentOutput:
        # a2a 1.1.2: create_client 自建网络层；send_message 需 SendMessageRequest 包装
        from a2a.client import ClientConfig, create_client
        from a2a.helpers import new_text_message
        from a2a.types import Role, SendMessageRequest

        # httpx 默认 read timeout 5s < LLM 生成长回复的静默期（此时无 tool
        # 事件可流）→ 客户端假超时而 server 仍在跑。放宽到 600s，与节点
        # 预算 DEFAULT_NODE_TIMEOUT_S 对齐；权威限额仍是外层 wait_for。
        # trust_env=False：A2A 端点是本机/内网地址，禁止吃系统代理
        #（否则回环流量被代理劫持回 502）。
        a2a_client = await create_client(node_url, ClientConfig(
            streaming=True,
            httpx_client=httpx.AsyncClient(
                trust_env=False,
                timeout=httpx.Timeout(connect=10.0, read=600.0, write=10.0,
                                      pool=10.0))))
        try:
            tracer.emit("agent_discovered", url=node_url)
            msg = new_text_message(
                agent_input.to_json(), role=Role.ROLE_USER,
                context_id=agent_input.run_id)  # trace_id 贯穿两进程
            final_text = ""
            async for chunk in a2a_client.send_message(
                    SendMessageRequest(message=msg)):
                if chunk.HasField("status_update"):
                    if task_id_box is not None:
                        task_id_box["task_id"] = chunk.status_update.task_id
                    text = _part_texts(chunk.status_update.status.message)
                    if text.startswith("agent_event:"):
                        try:
                            data = json.loads(text[len("agent_event:"):])
                            name = data.pop("event", "agent_event")
                            if name == "hitl_heartbeat" and budget is not None:
                                budget.extend(180.0)  # 心跳=有人在路上，预算续期
                            tracer.emit(name, **data)
                        except json.JSONDecodeError:
                            pass
                    elif text:  # 终止态携带的最终结果 JSON
                        final_text = text
                elif chunk.HasField("artifact_update") and not final_text:
                    final_text = _part_texts(chunk.artifact_update.artifact)
            if final_text:
                # 统一走契约层解析；非 JSON（多为 agent 侧失败原文）抛
                # OutputContractError，原文随异常进 trace（node_retry 可见）
                return parse_result(final_text)
            raise RuntimeError("no result in task stream")
        finally:
            await a2a_client.close()

    async def _cancel_task(self, node_url: str, task_id_box: dict,
                           tracer: Tracer) -> None:
        """A2A tasks/cancel：放弃等待时取消 server 端执行（不留孤儿任务）。"""
        task_id = task_id_box.get("task_id")
        if not task_id:
            return
        from a2a.client import ClientConfig, create_client
        from a2a.types import CancelTaskRequest

        client = await create_client(node_url, ClientConfig(
            streaming=True,
            httpx_client=httpx.AsyncClient(
                trust_env=False, timeout=httpx.Timeout(30.0))))
        try:
            await client.cancel_task(CancelTaskRequest(id=task_id))
            tracer.emit("task_cancel_sent", task_id=task_id)
        except Exception as e:
            tracer.emit("task_cancel_failed", task_id=task_id,
                        error=str(e)[:200])
        finally:
            await client.close()

    async def _shutdown_sandboxes(self, trace_id: str, tracer: Tracer,
                                  urls: set[str] | None = None) -> None:
        """广播 shutdown 到该 run 全部参与节点 server（防线层1）。

        只发主 server 是跨 server 回收盲点（预研 §3.1②）：其它 server 上因
        agent 用沙箱工具创建的 session 无人叫 shutdown。首个 worktree remove
        成功、其余幂等失败无害；单点失败 emit 后不重试不阻断（层2 TTL 兜底）。"""
        targets = sorted(set(urls)) if urls else [self._primary_url()]
        client, should_close = self._client()
        try:
            for url in targets:
                try:
                    r = await client.post(
                        f"{url}/admin/sandboxes/{trace_id}/shutdown")
                    tracer.emit("sandbox_destroy", url=url, http=r.status_code)
                except Exception as e:
                    tracer.emit("sandbox_destroy_failed", url=url, error=str(e))
        finally:
            if should_close:
                await client.aclose()


def _part_texts(obj) -> str:
    """从 proto Message / Artifact 等对象拼接 parts 里的 text。"""
    parts = getattr(obj, "parts", None) or []
    return "".join(p.text for p in parts if getattr(p, "text", None))
