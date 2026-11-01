"""HITL 等待注册表：agent_server 进程内阻塞等人的 Future 管理。

设计决策（见 docs/2026-09-19-web-streaming-hitl-design.md §3.2）：
- 无超时：人可以很久之后才答，答了接着 task 继续；三层 deadline 由心跳续期
  （engine wait_for / server hard_cap / httpx read timeout 都靠流上字节保活）
- 空 answer 返回确认话术——明确信号，防 agent 误解为缺值重问
- 跨进程答案转发走 agent_server 的 /internal/hitl side 路由
"""
from __future__ import annotations

import asyncio

CONFIRM_PHRASE = "(人工已确认继续，无补充信息)"


class HITLRegistry:

    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future] = {}

    def pending_for(self, trace_id: str) -> bool:
        return trace_id in self._pending

    async def wait(self, trace_id: str, heartbeat=None,
                   interval_s: float = 20.0) -> str:
        """阻塞等待人工输入。heartbeat 每 interval_s 调一次（保活+续期）。"""
        if trace_id in self._pending:
            raise RuntimeError(f"hitl already pending: {trace_id}")
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[trace_id] = fut
        try:
            while not fut.done():
                try:
                    return await asyncio.wait_for(
                        asyncio.shield(fut), interval_s)
                except TimeoutError:
                    if heartbeat:
                        heartbeat()  # 无超时设计：心跳后继续等
            return fut.result()
        finally:
            self._pending.pop(trace_id, None)

    def resolve(self, trace_id: str, text: str) -> bool:
        fut = self._pending.get(trace_id)
        if fut is None or fut.done():
            return False
        fut.set_result(text.strip() or CONFIRM_PHRASE)
        return True

    def cancel(self, trace_id: str) -> None:
        fut = self._pending.pop(trace_id, None)
        if fut and not fut.done():
            fut.cancel()


REGISTRY = HITLRegistry()
