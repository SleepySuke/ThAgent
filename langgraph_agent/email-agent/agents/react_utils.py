"""轻量 React 推理循环 — 替代 create_react_agent，直接使用 bind_tools + while 循环"""
import logging
from collections.abc import Callable

from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)

MAX_TURNS = 5


def run_react_loop(
    model: BaseChatModel,
    tools: list[BaseTool],
    system_prompt: str,
    user_context: str,
    max_turns: int = MAX_TURNS,
    result_extractor: Callable[[list], dict] | None = None,
) -> dict:
    """执行一次 React 推理循环。

    Args:
        model: LLM 实例
        tools: 工具列表
        system_prompt: 系统提示词
        user_context: 用户上下文（邮件内容、分类结果等）
        max_turns: 最大推理轮数
        result_extractor: 从最终消息列表提取 state 更新的函数

    Returns:
        state 更新 dict
    """
    model_with_tools = model.bind_tools(tools)
    messages: list = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_context),
    ]

    for turn in range(max_turns):
        try:
            response = model_with_tools.invoke(messages)
        except Exception as e:
            logger.error("LLM call failed at turn %d: %s", turn, e)
            break

        messages.append(response)

        if not response.tool_calls:
            logger.info("React loop finished at turn %d (no tool calls)", turn + 1)
            break

        for tc in response.tool_calls:
            tool_name = tc.get("name", "")
            tool_args = tc.get("args", {})
            tool_id = tc.get("id", "")

            matching = [t for t in tools if t.name == tool_name]
            if matching:
                try:
                    result = matching[0].invoke(tool_args)
                    logger.info("Tool %s executed", tool_name)
                except Exception as e:
                    result = f"Tool error: {e}"
                    logger.error("Tool %s failed: %s", tool_name, e)
            else:
                result = f"Unknown tool: {tool_name}"

            messages.append(ToolMessage(content=str(result), tool_call_id=tool_id))

    else:
        logger.warning("React loop reached max turns (%d)", max_turns)

    if result_extractor:
        return result_extractor(messages)
    return {}


def extract_last_message(messages: list) -> dict:
    """从消息列表中提取最后一条 AI 消息的 content"""
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return {"_react_result": msg.content}
    return {"_react_result": ""}


def extract_tool_results(messages: list, tool_name: str) -> list[str]:
    """提取特定工具的所有返回结果"""
    results = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            results.append(str(msg.content))
    return results
