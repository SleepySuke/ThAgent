"""九期裁定 2/3/4/5：engine 审阅门控 / replan 回路 / REVIEW_AUTO / node_start 钉桩。

in-proc fake engine（绕过 A2A，与 tests/integration/test_engine.py 同手法）。
"""
import asyncio
import dataclasses
import json

from harness.checkpoint import Checkpoint, load_checkpoint, save_checkpoint
from harness.contract import AgentOutput, ExecutionPlan
from harness.engine import HarnessEngine

CR_OUT = AgentOutput(output_data={"verdict": "ok", "issues": []},
                     artifact_url="", status="ok")
REPORT_OUT = AgentOutput(output_data={"summary": "s"}, artifact_url="",
                         status="ok")
EXEC_OUT = AgentOutput(output_data={"exit_code": 0}, artifact_url="",
                       status="ok")

REPORT_PLAN = ExecutionPlan(
    plan_id="p", nodes=[{"id": "cr", "agent": "cr_agent"},
                        {"id": "report", "agent": "report_agent"}],
    edges=[["cr", "report"]])


class _FakeEngine(HarnessEngine):
    """按 node_id 返回固定 output：绕过真实 A2A 测调度逻辑。"""

    def __init__(self, runs_root, outputs):
        super().__init__("http://127.0.0.1:1", runs_root)
        self._outputs = outputs
        self.sent = []

    async def _send(self, node_url, agent_input, tracer, task_id_box=None,
                    budget=None):
        self.sent.append(agent_input)
        return self._outputs[agent_input.node_id]


class _PlanEngine(_FakeEngine):
    """plan 由测试注入（依次返回），记录每次 _plan 收到的 payload。"""

    def __init__(self, runs_root, outputs, plans):
        super().__init__(runs_root, outputs)
        self._plans = list(plans)
        self.plan_payloads = []

    async def _plan(self, trace_id, payload, tracer, context_id):
        self.plan_payloads.append(dict(payload))
        return self._plans[min(len(self.plan_payloads) - 1,
                               len(self._plans) - 1)]


async def _wait_review(engine, trace_id, timeout=2.0):
    """轮询等 run 进入 REVIEW_PENDING（新一轮 review_event 已建未 set）。

    必须排除上一轮已 set 未消费的旧事件——否则裁决会打在旧门上被静默拒绝。"""
    async def ready():
        h = engine._runs.get(trace_id)
        return (h is not None and h.review_event is not None
                and not h.review_event.is_set())
    deadline = asyncio.get_running_loop().time() + timeout
    while not await ready():
        if asyncio.get_running_loop().time() > deadline:
            raise TimeoutError("not in review pending")
        await asyncio.sleep(0.01)


def _events(runs, trace_id):
    return [json.loads(line) for line in
            (runs / trace_id / "trace.jsonl").read_text().splitlines()]


def _triggers(events):
    return [e["payload"]["trigger"] for e in events
            if e["event"] == "state_transition"]


async def test_single_cr_no_report_completes_directly(tmp_path):
    # 矩阵 #1：无 report 节点 → 一期行为不变，直落 COMPLETED
    engine = _FakeEngine(tmp_path / "runs", {"cr_agent": CR_OUT})
    plan = ExecutionPlan(plan_id="d", nodes=[{"id": "cr", "agent": "cr_agent"}],
                         edges=[])
    await engine.execute_for("t1", {"repo": "x"}, plan)
    events = _events(tmp_path / "runs", "t1")
    assert "review_pending" not in [e["event"] for e in events]
    assert "SUBMIT_REVIEW" not in _triggers(events)
    assert events[-1]["payload"]["status"] == "ok"


async def test_accept_completes_with_review_trace(tmp_path):
    # 矩阵 #19：含 report → park 在 REVIEW_PENDING，accept 后 COMPLETED
    runs = tmp_path / "runs"
    engine = _FakeEngine(runs, {"cr_agent": CR_OUT, "report_agent": REPORT_OUT})
    task = asyncio.create_task(engine.execute_for("t2", {"repo": "x"},
                                                  REPORT_PLAN))
    await _wait_review(engine, "t2")
    engine.review_run("t2", "accept")
    await task
    triggers = _triggers(_events(runs, "t2"))
    assert "SUBMIT_REVIEW" in triggers and "REVIEW_ACCEPT" in triggers
    assert triggers.index("SUBMIT_REVIEW") < triggers.index("REVIEW_ACCEPT")
    assert engine.sent[-1].node_id == "report_agent"
    assert load_checkpoint(runs, "t2")["round"] == 1


async def test_reject_replans_with_feedback_round2(tmp_path):
    # 矩阵 #20：reject+feedback → round=2，planning 收 hitl_feedback，
    # 二轮不沿用一轮已完成节点（全新执行）
    runs = tmp_path / "runs"
    engine = _PlanEngine(runs, {"cr_agent": CR_OUT, "report_agent": REPORT_OUT},
                         [REPORT_PLAN, REPORT_PLAN])
    task = asyncio.create_task(engine.execute_for("t3", {"repo": "x"}))
    await _wait_review(engine, "t3")
    engine.review_run("t3", "reject", feedback="报告缺 pass_rate")
    # replan 后新报告再审（设计 §1：reject=PLANNING 重规划 → 再审）
    await _wait_review(engine, "t3")
    engine.review_run("t3", "accept")
    await task
    assert load_checkpoint(runs, "t3")["round"] == 2
    assert len(engine.plan_payloads) == 2
    assert engine.plan_payloads[1]["hitl_feedback"] == {
        "text": "报告缺 pass_rate"}
    # 二轮全新执行：cr 与 report 各跑两次
    assert [i.node_id for i in engine.sent] == ["cr_agent", "report_agent",
                                                "cr_agent", "report_agent"]
    events = _events(runs, "t3")
    assert any(e["event"] == "review_rejected" for e in events)


async def test_review_auto_env_skips_gate(tmp_path, monkeypatch):
    # 矩阵 #18：REVIEW_AUTO → 不等裁决，emit review_auto_accepted 直落 COMPLETED
    monkeypatch.setenv("AGENT_INFRA_REVIEW_AUTO", "1")
    runs = tmp_path / "runs"
    engine = _FakeEngine(runs, {"cr_agent": CR_OUT, "report_agent": REPORT_OUT})
    await engine.execute_for("t4", {"repo": "x"}, REPORT_PLAN)
    events = _events(runs, "t4")
    triggers = _triggers(events)
    assert "SUBMIT_REVIEW" not in triggers
    assert any(e["event"] == "review_auto_accepted" for e in events)
    assert events[-1]["payload"]["status"] == "ok"


async def test_review_run_idempotent_and_gated(tmp_path):
    # 矩阵 #2/#3：首个 set 生效；非审阅态 review_run False
    runs = tmp_path / "runs"
    engine = _FakeEngine(runs, {"cr_agent": CR_OUT, "report_agent": REPORT_OUT})
    task = asyncio.create_task(engine.execute_for("t5", {"repo": "x"},
                                                  REPORT_PLAN))
    assert engine.review_run("t5", "accept") is False   # 未到审阅态
    await _wait_review(engine, "t5")
    assert engine.review_run("t5", "accept") is True
    assert engine.review_run("t5", "reject", feedback="x") is False  # 已 set
    await task
    assert engine.review_run("t5", "reject") is False   # handle 已 pop


async def test_reject_empty_feedback_normalizes_none(tmp_path):
    # 四期教训：feedback 为空 → hitl_feedback 归一 None，不残留上次注入
    runs = tmp_path / "runs"
    engine = _PlanEngine(runs, {"cr_agent": CR_OUT, "report_agent": REPORT_OUT},
                         [REPORT_PLAN, REPORT_PLAN])
    task = asyncio.create_task(engine.execute_for("t6", {"repo": "x"}))
    await _wait_review(engine, "t6")
    engine.review_run("t6", "reject")
    await _wait_review(engine, "t6")   # 二轮再审
    engine.review_run("t6", "accept")
    await task
    assert engine.plan_payloads[1]["hitl_feedback"] is None


async def test_node_start_pins_model_and_prompt_sha(tmp_path, monkeypatch):
    # 裁定 5：agent 节点钉 model + prompt_sha（12 hex）；program 节点两者 ""
    from harness import programs
    monkeypatch.setenv("AGENT_INFRA_REVIEW_AUTO", "1")  # 只看 node_start，不进审阅
    monkeypatch.setitem(programs.PROGRAM_HANDLERS, "execute_cases",
                        lambda *a, **k: EXEC_OUT.output_data)
    runs = tmp_path / "runs"
    engine = _FakeEngine(runs, {"report_agent": REPORT_OUT})
    plan = ExecutionPlan(
        plan_id="p", nodes=[{"id": "exec", "program": "case_executor"},
                            {"id": "report", "agent": "report_agent"}],
        edges=[["exec", "report"]])
    await engine.execute_for("t7", {"repo": "x"}, plan)
    starts = {e["node_id"]: e["payload"]
              for e in _events(runs, "t7") if e["event"] == "node_start"}
    sha = starts["report"]["prompt_sha"]
    assert len(sha) == 12 and all(c in "0123456789abcdef" for c in sha)
    assert starts["report"]["model"]          # 解析出节点模型（非空）
    assert starts["exec"]["model"] == ""
    assert starts["exec"]["prompt_sha"] == ""


async def test_pause_and_review_coexist(tmp_path):
    # 矩阵 #21b：执行中 pause→resume 照常工作，之后仍正确进入审阅门控
    runs = tmp_path / "runs"

    class _SlowEngine(_FakeEngine):
        async def _send(self, node_url, agent_input, tracer, task_id_box=None,
                        budget=None):
            await asyncio.sleep(0.2)
            return await super()._send(node_url, agent_input, tracer,
                                       task_id_box, budget)

    engine = _SlowEngine(runs, {"cr_agent": CR_OUT,
                                "report_agent": REPORT_OUT})
    task = asyncio.create_task(engine.execute_for("t8", {"repo": "x"},
                                                  REPORT_PLAN))
    await asyncio.sleep(0.05)                 # 卡在 cr 执行中
    assert await engine.pause_run("t8") is True
    engine.resume_run("t8", text="补充意见")
    await _wait_review(engine, "t8")          # resume 跑完后进审阅门控
    engine.review_run("t8", "accept")
    await task
    triggers = _triggers(_events(runs, "t8"))
    assert "NEED_HUMAN_INPUT" in triggers and "SUBMIT_REVIEW" in triggers


async def test_old_checkpoint_without_round_reads_as_1(tmp_path):
    # 裁定 6 / V2a-3：旧 checkpoint 无 round 键 → loader 兼容默认 1
    cp = Checkpoint(run_id="r1", context_id="r1", current_node="cr",
                    harness_state="executing")
    data = dataclasses.asdict(cp)
    data.pop("round")
    data["version"] = 1
    save_checkpoint(tmp_path, "r1", data)
    assert load_checkpoint(tmp_path, "r1")["round"] == 1




async def test_replan_round_pause_resume_keeps_progress(tmp_path):
    """t4-rev Important 回归：replan 轮内 pause→resume 不得清本轮进度。

    修复前 _start_body 用 round>1 重算 fresh——round 2 里暂停再恢复会把本轮
    已完成节点清掉整轮重跑（cr 发送 3 次）。修复后 fresh 是 consume-once
    标志，pause→resume 重入不再清盘（cr 恰好 2 次：一轮各一）。"""
    runs = tmp_path / "runs"

    class _SlowReport(_PlanEngine):
        async def _send(self, node_url, agent_input, tracer, task_id_box=None,
                        budget=None):
            if agent_input.node_id == "report_agent":
                await asyncio.sleep(0.2)   # report 在飞时可 pause
            return await super()._send(node_url, agent_input, tracer,
                                       task_id_box, budget)

    engine = _SlowReport(runs, {"cr_agent": CR_OUT,
                                "report_agent": REPORT_OUT},
                         plans=[REPORT_PLAN, REPORT_PLAN])
    task = asyncio.create_task(
        engine.execute_for("t9", {"repo": "x"}, None))   # None → 走注入 plan
    await _wait_review(engine, "t9")
    engine.review_run("t9", "reject", "第一版不够")       # → round 2（fresh 清盘一次）
    # 等 round 2 的 cr 已完成、report 在飞
    deadline = asyncio.get_running_loop().time() + 2.0
    while len([s for s in engine.sent if s.node_id == "cr_agent"]) < 2:
        assert asyncio.get_running_loop().time() < deadline, "round2 cr 未起"
        await asyncio.sleep(0.01)
    await asyncio.sleep(0.05)                     # report 已进入 0.2s 慢段
    assert await engine.pause_run("t9") is True   # round 2 执行中打断
    engine.resume_run("t9")
    await _wait_review(engine, "t9")
    engine.review_run("t9", "accept")
    await task
    cr_n = len([s for s in engine.sent if s.node_id == "cr_agent"])
    assert cr_n == 2, f"cr 重跑={cr_n}（pause→resume 清掉了 round2 进度）"
    assert len(engine.plan_payloads) == 2          # reject 只重规划一次


async def test_accept_persists_completed_checkpoint(tmp_path):
    """t5-rev Critical 回归：accept 后 checkpoint 必须落 completed。

    修复前 accept 路径无终态落盘（伪码即漏，被 app 测试 fake 代写掩盖）——
    run_status 审阅面永久误报待裁决、boot_sweep 终态回收永不生效。"""
    runs = tmp_path / "runs"
    engine = _FakeEngine(runs, {"cr_agent": CR_OUT, "report_agent": REPORT_OUT})
    task = asyncio.create_task(
        engine.execute_for("t10", {"repo": "x"}, REPORT_PLAN))
    await _wait_review(engine, "t10")
    engine.review_run("t10", "accept")
    await task
    assert load_checkpoint(runs, "t10")["harness_state"] == "completed"
    assert load_checkpoint(runs, "t10")["round"] == 1


async def test_no_report_chain_persists_completed(tmp_path):
    """同根第二面：无 report 直落路径也落 completed（boot_sweep 依赖终态）。"""
    runs = tmp_path / "runs"
    engine = _FakeEngine(runs, {"cr_agent": CR_OUT})
    await engine.execute_for("t11", {"repo": "x"},
                             ExecutionPlan(plan_id="s",
                                           nodes=[{"id": "cr",
                                                   "agent": "cr_agent"}],
                                           edges=[]))
    assert load_checkpoint(runs, "t11")["harness_state"] == "completed"
