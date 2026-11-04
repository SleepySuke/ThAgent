"""Requirement Agent 组装：需求/commit → 结构化任务说明（cr 的上游增益）。"""
from __future__ import annotations

import os
import shlex
from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from harness.callbacks import build_callbacks
from harness.config import register_model_capabilities, resolve_model
from harness.contract import RunContext
from harness.policy import NodePolicy
from harness.sandbox.manager import SandboxManager
from harness.tools import build_tools

_AGENT_DIR = Path(__file__).parent

# MCP 暴露面（坑 #16：与 harness/policy.py requirement 白名单同步——ADK MCP
# 工具默认裸名无 server 前缀，实测 tools/list 返回 'get_pr'）
MCP_TOOL_NAMES = ["get_pr"]


def _build_mcp_toolset():
    """opt-in MCP 挂载：AGENT_INFRA_MCP_CMD 提供启动命令（shlex 解析）时挂
    McpToolset（stdio transport）；无 env 时返回 None——默认路径零改动、零
    mcp import（延迟导入）。

    进程生命周期：close() 关 MCP 会话 → stdio_client AsyncExitStack unwind，
    terminate_on_close=True 杀子进程。**回收入口是 agent_server.adk_run 的
    finally `await runner.close()`**（Runner.close 是 ADK 唯一回收 toolset 的
    路径，run_async 不收——t7-rev Important：此前误写「框架托管」，实际无人
    调用则每 run 泄漏一个 stdio 子进程）。

    已知天花板：MCP 工具不经 harness/tools/_base 的 _wrap（FACTORIES 之外的
    Toolset）——deadline 由 MCP 客户端/服务端自身语义承担，harness 侧治理面
    目前只有 policy 白名单。
    """
    cmd = os.environ.get("AGENT_INFRA_MCP_CMD")
    if not cmd:
        return None
    from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
    from mcp import StdioServerParameters

    parts = shlex.split(cmd)
    return McpToolset(connection_params=StdioServerParameters(
        command=parts[0], args=parts[1:]), tool_filter=list(MCP_TOOL_NAMES))


def build_agent(run: RunContext, manager: SandboxManager,
                policy: NodePolicy) -> LlmAgent:
    # 两级模型解析：AGENT_INFRA_MODEL_REQUIREMENT_AGENT > AGENT_INFRA_MODEL > 默认
    model = resolve_model("requirement_agent", "zai/glm-4.6")
    register_model_capabilities()
    llm_kwargs = ({"extra_body": {"thinking": {"type": "disabled"}}}
                  if model.startswith("zai/glm-4") else {})
    # 条件挂载：opt-in MCP（PR 上下文），无 env 时零改动默认路径
    mcp_toolset = _build_mcp_toolset()
    tools = build_tools(run, manager, ["read_diff", "read_file", "list_files"])
    if mcp_toolset is not None:
        tools = [*tools, mcp_toolset]
    return LlmAgent(
        name="requirement_agent",
        model=LiteLlm(model=model, **llm_kwargs),
        instruction=(_AGENT_DIR / "prompt.md").read_text(encoding="utf-8"),
        description="把需求与 commit 改动翻译成结构化任务说明（类型/范围/风险/验收）",
        tools=tools,
        **build_callbacks(run, policy),
    )
