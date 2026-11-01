"""ToolSpec 统一包装器：deadline / 错误分型 / 结果 cap / 声明表治理面。"""
import asyncio

from harness.tools import FACTORIES
from harness.tools._base import _SPECS, ToolSpec, _wrap


async def test_deadline_timeout_returns_error_dict():
    # 矩阵 #15 批屏障治理：慢工具被 wait_for 掐断，错误回模型不炸 run
    async def slow() -> dict:
        await asyncio.sleep(0.2)
        return {"ok": True}

    out = await _wrap(ToolSpec("slow", "network", deadline_s=0.05))(slow)()
    assert out["error"]["kind"] == "timeout"
    assert "message" in out["error"]


async def test_error_typed_and_top_level_error_key():
    """顶层保留 "error" 键（坑 #18：前端 glyph regex / smoke 消费方后向兼容）。"""
    async def boom() -> dict:
        raise RuntimeError("disk on fire")

    out = await _wrap(ToolSpec("boom", "exec"))(boom)()
    assert "error" in out                       # 顶层键在（旧形状的兼容面）
    assert out["error"]["kind"] == "exec_failed"
    assert "disk on fire" in out["error"]["message"]


async def test_result_cap_truncates_and_flags():
    long = "x" * 50_000
    out = await _wrap(ToolSpec("big", "read", max_result_chars=100))(
        _mk({"content": long, "note": "short"}))()
    assert len(out["content"]) == 100
    assert out["truncated"] is True
    assert out["note"] == "short"               # 未超限的值不动


def _mk(value):
    async def fn() -> dict:
        return value
    return fn


def test_specs_cover_all_factories():
    """治理面钉桩：新增工具漏声明 ToolSpec 即红（工具名 == 白名单，坑 #17）。"""
    assert set(_SPECS) == set(FACTORIES)
