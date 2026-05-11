# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-11
@Description：
智扫通 Agent 编排层。
基于 langchain.agents.create_agent 组装模型、工具、Middleware，
提供同步执行（execute）和流式执行（execute_stream）两个入口。

Middleware：
- prompt_switcher: 根据用户消息关键词动态切换 system prompt
- agent_middleware: LLM 调用前后日志 + 工具调用监控
  两者均在 create_sweep_robot_agent 创建时传入，调用方无需额外注入。
'''
from langchain.agents import create_agent

from middleware.agent_middleware import create_middleware_from_config
from middleware.prompt_switcher import build_prompt_middleware
from model.factory import get_model_factory
from tools import get_agent_tools
from utils.prompt_handler import load_prompt_bundle


# ---------------------------------------------------------------------------
# Agent 创建
# ---------------------------------------------------------------------------

def create_sweep_robot_agent():
    """创建智扫通 Agent，组合模型、工具、动态 prompt 和观测 Middleware。"""
    model = get_model_factory().create_chat_model()
    tools = get_agent_tools()
    bundle = load_prompt_bundle()

    middleware = [
        build_prompt_middleware(bundle),
        *create_middleware_from_config(),
    ]

    return create_agent(
        model=model,
        tools=tools,
        middleware=middleware,
    )


# ---------------------------------------------------------------------------
# 执行入口
# ---------------------------------------------------------------------------

def _extract_answer(result: dict) -> str:
    """从 Agent 执行结果中提取最后一条有实际文本内容的 AI 消息。"""
    for msg in reversed(result.get("messages", [])):
        if getattr(msg, "type", None) == "ai" and getattr(msg, "content", "").strip():
            return msg.content
    return ""


def execute(agent, query: str) -> str:
    """同步执行 Agent 查询，返回最终回答字符串。"""
    result = agent.invoke({"messages": [("user", query)]})
    return _extract_answer(result)


def execute_stream(agent, query: str):
    """流式执行 Agent 查询，逐块产出响应。"""
    yield from agent.stream(
        {"messages": [("user", query)]},
        stream_mode="updates",
    )
