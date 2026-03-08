# -*- coding: UTF-8 -*-
'''
@Author ：自然醒
@Version ：1.0
'''

import asyncio
import os
from agents.extensions.models.litellm_model import LitellmModel

from pydantic import BaseModel

from agents import Agent, AgentBase, ModelSettings, RunContextWrapper, Runner, trace
from agents.tool import function_tool
from agents import set_tracing_disabled

from auto_mode import confirm_with_fallback, input_with_fallback

"""
本示例演示了带条件启用功能的“智能体即工具”模式。
智能体工具根据用户访问级别通过 is_enabled 参数动态启用/禁用。
"""


class AppContext(BaseModel):
    language_preference: str = "English_only"  # "spanish_only"（仅西班牙语）, "french_spanish"（法语+西班牙语）, "european"（欧洲语言）


def french_spanish_enabled(ctx: RunContextWrapper[AppContext], agent: AgentBase) -> bool:
    """为法语+西班牙语和欧洲偏好启用。"""
    return ctx.context.language_preference in ["Chinese", "English"]


def european_enabled(ctx: RunContextWrapper[AppContext], agent: AgentBase) -> bool:
    """仅为欧洲偏好启用。"""
    return ctx.context.language_preference == "China and UK"


@function_tool(needs_approval=True)
async def get_user_name() -> str:
    print("正在获取用户名...")
    return "苏可进"


set_tracing_disabled = True
qwen_model = LitellmModel(model="dashscope/qwen-plus-2025-12-01")
os.environ["OPENAI_API_KEY"] = ""

# 创建专门化智能体
chinese_agent = Agent(
    name="chinese_agent",
    instructions="你用中文回应。始终用中文回答用户的问题。你必须调用所有工具以最佳地回答用户的问题。",
    model_settings=ModelSettings(tool_choice="required"),
    model=qwen_model,
    tools=[get_user_name],
)

english_agent = Agent(
    name="english_agent",
    instructions="你用英文回应。始终用法语回答用户的问题。",
    model=qwen_model
)

italian_agent = Agent(
    name="italian_agent",
    instructions="你用意大利语回应。始终用意大利语回答用户的问题。",
    model=qwen_model
)

# 创建带条件工具的中控智能体
orchestrator = Agent(
    name="orchestrator",
    instructions=(
        "你是一个多语言助手。你使用给定的工具来响应用户。"
        "你必须调用所有可用的工具来提供不同语言的回应。"
        "你从不自己用语言回应，总是使用提供的工具。"
    ),
    tools=[
        chinese_agent.as_tool(
            tool_name="respond_chinese",
            tool_description="用中文回答用户的问题",
            is_enabled=True,  # 始终启用
            needs_approval=True,  # 需要人工批准
        ),
        english_agent.as_tool(
            tool_name="respond_english",
            tool_description="用英文回答用户的问题",
            is_enabled=french_spanish_enabled,
        ),
        italian_agent.as_tool(
            tool_name="respond_italian",
            tool_description="用意大利语回答用户的问题",
            is_enabled=european_enabled,
        ),
    ],
    model=qwen_model,
)


async def main():
    """带有LLM交互的交互式演示。"""
    print("智能体即工具——条件启用示例\n")
    print("本示例演示如何根据用户偏好动态启用语言响应工具。\n")

    print("选择语言偏好：")
    print("1. 仅英语（1个工具）")
    print("2. 中文和英语（2个工具）")
    print("3. 中国和英国语言（3个工具）")

    choice = input_with_fallback("\n请选择选项 (1-3): ", "2").strip()
    preference_map = {"1": "仅英语", "2": "中文", "3": "中国和英国语言"}
    language_preference = preference_map.get(choice, "仅英语")

    # 创建上下文并显示可用工具
    context = RunContextWrapper(AppContext(language_preference=language_preference))
    available_tools = await orchestrator.get_all_tools(context)
    tool_names = [tool.name for tool in available_tools]

    print(f"\n语言偏好: {language_preference}")
    print(f"可用工具: {', '.join(tool_names)}")
    print(f"LLM 只能看到并使用这 {len(available_tools)} 个工具\n")

    # 获取用户请求
    user_request = input_with_fallback(
        "提出一个问题，并查看可用语言的回应：\n",
        "早上好怎么说？",
    )

    # 运行LLM交互
    print("\n正在处理请求...")
    with trace("条件工具访问"):
        result = await Runner.run(
            starting_agent=orchestrator,
            input=user_request,
            context=context.context,
        )
        while result.interruptions:

            async def confirm(question: str) -> bool:
                return confirm_with_fallback(f"{question} (y/n): ", default=True)

            state = result.to_state()
            for interruption in result.interruptions:
                prompt = f"\n您是否批准此工具调用: {interruption.name} 参数 {interruption.arguments}?"
                confirmed = await confirm(prompt)
                if confirmed:
                    state.approve(interruption)
                    print(f"✓ 已批准: {interruption.name}")
                else:
                    state.reject(interruption)
                    print(f"✗ 已拒绝: {interruption.name}")
            result = await Runner.run(orchestrator, state)

    print(f"\n回应:\n{result.final_output}")


if __name__ == "__main__":
    asyncio.run(main())
