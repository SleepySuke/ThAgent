"""真实 MCP server smoke（opt-in，烧不到 LLM）：挂 McpToolset → 列举工具 →
调一次 get_pr。用法见 Makefile `smoke-mcp`。

真实 GitHub MCP server 是外部二进制/Docker（npx/docker 命令），不进测试、
不进 CI；本脚本仅在显式提供 env 时手动执行。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import ClassVar

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # 让 agents 包可从项目根 import（同 smoke_hitl）


class _Ctx:
    """McpTool.run_async 的最小 ToolContext 鸭子类型（无 LLM 会话）。"""

    tool_confirmation = None
    custom_metadata: ClassVar[dict] = {}

    def request_confirmation(self, **kw):
        raise AssertionError("get_pr 不应请求确认")


async def main() -> int:
    from agents.requirement_agent.agent import MCP_TOOL_NAMES, _build_mcp_toolset

    toolset = _build_mcp_toolset()
    if toolset is None:
        print("AGENT_INFRA_MCP_CMD 未设置", file=sys.stderr)
        return 2
    try:
        tools = await toolset.get_tools()
        names = sorted(t.name for t in tools)
        print(f"tools: {names}")
        assert set(MCP_TOOL_NAMES) <= set(names), \
            f"白名单工具缺失: 期望 {MCP_TOOL_NAMES}, 实得 {names}"
        # get_pr 可调用性 smoke：pr_number=1（真实 GitHub server 上退化为
        # 一次真实 API 调用，仅验证链路通）
        tool = next(t for t in tools if t.name == "get_pr")
        res = await tool.run_async(args={"pr_number": 1}, tool_context=_Ctx())
        print(json.dumps(res, ensure_ascii=False)[:400])
        return 0
    finally:
        await toolset.close()  # 杀 stdio 子进程，不留孤儿


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
