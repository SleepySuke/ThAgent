"""MCPToolset × fake stdio server 真跑 e2e（零 LLM）：挂载→列举→调用→清理。

fake server（tests/mcp/fake_pr_server.py，纯 stdlib）由 MCPToolset 以 stdio
transport 拉起为子进程；工具调用用 duck-typed ToolContext 直测，不起 LLM 会话。
"""
import json
import sys
from pathlib import Path
from typing import ClassVar

import pytest
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from mcp import StdioServerParameters

# 绝对路径：不依赖 cwd，pgrep 匹配绝对路径串避免并行工作树误伤（t7-rev Minor）
FAKE_SERVER = [str(Path(__file__).resolve().parents[1] / "mcp"
                    / "fake_pr_server.py")]


def _toolset() -> McpToolset:
    return McpToolset(
        connection_params=StdioServerParameters(
            command=sys.executable, args=FAKE_SERVER),
        tool_filter=["get_pr"],
    )


class _Ctx:
    """McpTool.run_async 所需的最小 ToolContext 鸭子类型（无 LLM 会话）。"""

    tool_confirmation = None
    custom_metadata: ClassVar[dict] = {}

    def request_confirmation(self, **kw):  # pragma: no cover - 不应被触达
        raise AssertionError("get_pr 不应请求确认")


@pytest.fixture
async def toolset():
    ts = _toolset()
    yield ts
    # 清理语义：close() 关 MCP 会话 → stdio_client AsyncExitStack unwind，
    # terminate_on_close=True 杀子进程（不留孤儿）
    await ts.close()


async def test_mount_and_tool_name_matches_policy(toolset):
    """挂载成功且工具名与 policy 白名单一致（裸名，坑 #16）。"""
    names = {t.name for t in await toolset.get_tools()}
    assert names == {"get_pr"}
    from harness.policy import NODE_POLICIES
    assert names <= NODE_POLICIES["requirement_agent"].allowed_tools


async def test_get_pr_pr1_returns_canned(toolset):
    tool = (await toolset.get_tools())[0]
    res = await tool.run_async(args={"pr_number": 1}, tool_context=_Ctx())
    assert res["isError"] is False
    data = json.loads(res["content"][0]["text"])
    assert data["title"] == "Fix discount stack overflow in pricing"
    assert data["files"] == ["shop/pricing.py", "tests/test_pricing.py"]


async def test_get_pr_pr2_returns_other_canned(toolset):
    tool = (await toolset.get_tools())[0]
    res = await tool.run_async(args={"pr_number": 2}, tool_context=_Ctx())
    data = json.loads(res["content"][0]["text"])
    assert data["files"] == ["api/export.py"]  # 与 pr=1 的 canned 互异


async def test_close_kills_subprocess():
    """close() 后子进程退出干净（不留孤儿）。"""
    import asyncio

    ts = _toolset()
    await ts.get_tools()  # 触发 stdio 子进程拉起
    pattern = FAKE_SERVER[0]
    await ts.close()
    # 短暂等待子进程退出，然后确认没有 fake_pr_server 进程存活
    await asyncio.sleep(0.5)
    out = await asyncio.create_subprocess_exec(
        "pgrep", "-f", pattern,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    stdout, _ = await out.communicate()
    assert out.returncode != 0, f"孤儿进程: {stdout.decode()}"
