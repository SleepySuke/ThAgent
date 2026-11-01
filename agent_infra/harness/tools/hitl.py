"""T 层：HITL 工具。agent 在 ReAct loop 内按需调用，与沙箱工具同级。

question 经 tool_call 事件外发（前端 HITL 卡），答案由 /internal/hitl
side 路由 resolve 进 Future。无超时等待 + 20s 心跳（设计 §3.2）。
"""
from __future__ import annotations

import os

from harness.contract import RunContext
from harness.hitl import CONFIRM_PHRASE, REGISTRY

HEARTBEAT_S = 20.0


def request_human(run: RunContext, session) -> callable:
    async def request_human(question: str) -> str:
        """向人工请求补充信息（HITL）。仅在关键信息缺失且现有工具拿不到时使用。

        Args:
            question: 向人提出的具体问题（一句话，含必要上下文）。
        """
        # 无人值守评测/CI 模式下没人答题，HITL 无超时等待会挂死 run——
        # auto 模式立即确认继续（语义同空 answer：resolve 落 CONFIRM_PHRASE）。
        # env 在 agent server 进程读，须随 make eval-ab 起服时注入。
        if os.environ.get("AGENT_INFRA_HITL_AUTO"):
            return CONFIRM_PHRASE
        q = (question or "").strip()
        if not q or len(q) > 2000:
            return "(问题无效：请给出具体、非空的问题)"
        return await REGISTRY.wait(
            run.trace_id,
            heartbeat=lambda: run.event_sink("hitl_heartbeat",
                                             {"trace_id": run.trace_id}),
            interval_s=HEARTBEAT_S)
    # 内层函数名即工具名（ADK FunctionTool 靠 __name__ 标识），必须与白名单一致
    return request_human
