import asyncio

import pytest

from harness.hitl import HITLRegistry


async def test_wait_resolves_with_answer():
    reg = HITLRegistry()

    async def answer_later():
        await asyncio.sleep(0.05)
        assert reg.resolve("t1", "上限是 0.20") is True

    got = await asyncio.gather(reg.wait("t1"), answer_later())
    assert got[0] == "上限是 0.20"
    assert not reg.pending_for("t1")          # 用完即清


async def test_empty_answer_returns_confirmation_phrase():
    reg = HITLRegistry()

    async def answer_later():
        await asyncio.sleep(0.02)
        reg.resolve("t1", "")

    got = await asyncio.gather(reg.wait("t1"), answer_later())
    assert got[0] == "(人工已确认继续，无补充信息)"


async def test_heartbeat_called_while_waiting():
    reg = HITLRegistry()
    beats = []

    async def answer_later():
        await asyncio.sleep(0.12)
        reg.resolve("t1", "ok")

    await asyncio.gather(
        reg.wait("t1", heartbeat=lambda: beats.append(1), interval_s=0.03),
        answer_later())
    assert len(beats) >= 2                     # 等待期间心跳持续


async def test_no_timeout_long_wait():
    reg = HITLRegistry()

    async def answer_late():
        await asyncio.sleep(0.3)               # 远超 interval
        reg.resolve("t1", "late")

    got = await asyncio.gather(
        reg.wait("t1", heartbeat=lambda: None, interval_s=0.02), answer_late())
    assert got[0] == "late"                    # 无超时：晚到也接着走


async def test_cancel_clears_and_wait_raises():
    reg = HITLRegistry()
    task = asyncio.create_task(reg.wait("t1"))
    await asyncio.sleep(0.02)
    reg.cancel("t1")
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not reg.pending_for("t1")


async def test_double_wait_same_trace_rejected():
    reg = HITLRegistry()
    t1 = asyncio.create_task(reg.wait("t"))
    await asyncio.sleep(0.02)
    with pytest.raises(RuntimeError):
        await reg.wait("t")
    reg.cancel("t")
    await asyncio.gather(t1, return_exceptions=True)


def test_resolve_unknown_returns_false():
    assert HITLRegistry().resolve("nope", "x") is False
