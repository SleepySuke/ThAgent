# -*- coding: UTF-8 -*-
'''
@Author ：自然醒
@Version ：1.0
Agent 团队 - 基于 Google ADK 框架
weather_agent 作为根代理，管理 greeting_agent 和 farewell_agent
'''
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from dotenv import load_dotenv
from google.adk.sessions import InMemorySessionService
import asyncio
from google.adk.runners import Runner
from google.genai import types
import warnings
from google.adk.agents.callback_context import CallbackContext
from google.adk.models import LlmRequest, LlmResponse
from typing import Optional, Dict, Any
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.tool_context import ToolContext

warnings.filterwarnings("ignore")

import logging
logging.basicConfig(level=logging.ERROR)

load_dotenv()


# ==================== 工具定义 ====================

def get_weather(city: str) -> dict:
    """获取指定城市的当前天气报告。

    Args:
        city (str): 城市名称（如"北京"、"上海"、"深圳"）。

    Returns:
        dict: 包含天气信息的字典。
    """
    print(f"--- 工具: get_weather 被调用，城市: {city} ---")
    city_normalized = city.lower().replace(" ", "")

    mock_weather_db = {
        "北京": {"status": "success", "report": "北京今天天气晴朗，气温18摄氏度，空气质量良好，适合户外活动。"},
        "上海": {"status": "success", "report": "上海今天多云转晴，气温22摄氏度，有轻微雾霾，建议佩戴口罩。"},
        "深圳": {"status": "success", "report": "深圳今天晴间多云，气温28摄氏度，紫外线较强，注意防晒。"},
        "newyork": {"status": "success", "report": "纽约天气晴朗，气温25摄氏度。"},
        "london": {"status": "success", "report": "伦敦多云，气温15摄氏度。"},
        "tokyo": {"status": "success", "report": "东京小雨，气温18摄氏度。"},
    }

    if city in mock_weather_db:
        return mock_weather_db[city]
    elif city_normalized in mock_weather_db:
        return mock_weather_db[city_normalized]
    else:
        return {"status": "error", "error_message": f"抱歉，暂时没有'{city}'的天气信息。"}


def get_weather_stateful(city: str, tool_context: ToolContext) -> dict:
    """获取指定城市的当前天气报告（状态感知版本）。

    根据用户偏好设置的温度单位返回天气报告。

    Args:
        city (str): 城市名称（如"北京"、"上海"、"深圳"）。

    Returns:
        dict: 包含天气信息的字典，温度单位根据用户偏好调整。
    """
    print(f"--- 工具: get_weather_stateful 被调用，城市: {city} ---")

    temp_unit = tool_context.state.get("user:temperature_unit", "摄氏度")
    print(f"--- 当前温度单位偏好: {temp_unit} ---")

    mock_weather_db = {
        "北京": {"temp_c": 18, "condition": "晴朗", "air_quality": "良好"},
        "上海": {"temp_c": 22, "condition": "多云转晴", "air_quality": "轻微雾霾"},
        "深圳": {"temp_c": 28, "condition": "晴间多云", "air_quality": "良好"},
    }

    if city not in mock_weather_db:
        return {"status": "error", "error_message": f"抱歉，暂时没有'{city}'的天气信息。"}

    weather_data = mock_weather_db[city]
    temp_c = weather_data["temp_c"]

    if temp_unit == "华氏度":
        temp = round(temp_c * 9 / 5 + 32, 1)
        temp_str = f"{temp}华氏度"
    else:
        temp = temp_c
        temp_str = f"{temp}摄氏度"

    report = (
        f"{city}今天天气{weather_data['condition']}，气温{temp_str}，"
        f"空气质量{weather_data['air_quality']}。"
    )

    return {
        "status": "success",
        "report": report,
        "city": city,
        "temperature": temp,
        "unit": temp_unit,
    }


def say_hello(name: str = "朋友") -> str:
    """向用户发送友好的问候。

    Args:
        name (str): 用户名称，默认为"朋友"。

    Returns:
        str: 问候语。
    """
    print(f"--- 工具: say_hello 被调用，名称: {name} ---")
    return f"你好，{name}！很高兴见到你，有什么我可以帮助你的吗？"


def say_goodbye(name: str = "朋友") -> str:
    """向用户发送告别语。

    Args:
        name (str): 用户名称，默认为"朋友"。

    Returns:
        str: 告别语。
    """
    print(f"--- 工具: say_goodbye 被调用，名称: {name} ---")
    return f"再见，{name}！祝你今天愉快，期待下次再见！"



def block_keyword_guardrail(
    callback_context: CallbackContext, llm_request: LlmRequest
) -> Optional[LlmResponse]:
    """
    检查最新用户消息中是否包含 'BLOCK'。如果找到，则阻止 LLM 调用
    并返回预定义的 LlmResponse。否则返回 None 继续正常流程。
    """
    agent_name = callback_context.agent_name
    print(f"--- 回调: block_keyword_guardrail 正在运行，代理: {agent_name} ---")

    last_user_message_text = ""
    if llm_request.contents:
        for content in reversed(llm_request.contents):
            if content.role == 'user' and content.parts:
                # Assuming text is in the first part for simplicity
                if content.parts[0].text:
                    last_user_message_text = content.parts[0].text
                    break # Found the last user message text

    print(f"--- 回调: 检查最后一条用户消息: '{last_user_message_text[:100]}...' ---")

    # --- Guardrail Logic ---
    keyword_to_block = "BLOCK"
    if keyword_to_block in last_user_message_text.upper():
        print(f"--- 回调: 发现 '{keyword_to_block}'。阻止 LLM 调用！ ---")
        callback_context.state["guardrail_block_keyword_triggered"] = True
        print(f"--- 回调: 设置状态 'guardrail_block_keyword_triggered': True ---")

        # Construct and return an LlmResponse to stop the flow and send this back instead
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text=f"我无法处理此请求，因为它包含被阻止的关键词 '{keyword_to_block}'。")],
            )
            # Note: You could also set an error_message field here if needed
        )
    else:
        print(f"--- 回调: 未发现关键词。允许 {agent_name} 的 LLM 调用。 ---")
        return None

print("✅ block_keyword_guardrail 函数已定义。")   


def block_paris_tool_guardrail(
    tool: BaseTool,
    args: Dict[str, Any],
    tool_context: ToolContext,
) -> Optional[Dict[str, Any]]:
    """
    工具护栏：检查工具参数中是否包含 '巴黎'。
    如果城市参数为巴黎，则返回错误字典阻止工具执行。
    否则返回 None 允许工具继续执行。
    """
    tool_name = tool.name
    print(f"--- 工具护栏: block_paris_tool_guardrail 正在运行，工具: {tool_name} ---")
    print(f"--- 工具护栏: 检查参数: {args} ---")

    city = args.get("city", "")
    if city and "巴黎" in city:
        print(f"--- 工具护栏: 发现被阻止的城市 '{city}'。阻止工具执行！ ---")
        tool_context.state["guardrail_block_paris_triggered"] = True
        print(f"--- 工具护栏: 设置状态 'guardrail_block_paris_triggered': True ---")

        return {
            "status": "error",
            "error_message": f"抱歉，系统暂时禁止查询 '{city}' 的天气信息。"
        }

    print(f"--- 工具护栏: 城市参数正常。允许工具 {tool_name} 执行。 ---")
    return None

print("✅ block_paris_tool_guardrail 函数已定义。")   


# ==================== 子代理定义 ====================

greeting_agent = LlmAgent(
    model=LiteLlm(model="dashscope/qwen-plus"),
    name="greeting_agent",
    description="专门处理问候请求。当用户打招呼、问好或自我介绍时，委派给此代理。",
    instruction="你是问候专家。使用 'say_hello' 工具向用户发送友好的问候，用中文回答。",
    tools=[say_hello],
)

farewell_agent = LlmAgent(
    model=LiteLlm(model="dashscope/qwen-plus"),
    name="farewell_agent",
    description="专门处理告别请求。当用户说再见、离开或结束对话时，委派给此代理。",
    instruction="你是告别专家。使用 'say_goodbye' 工具向用户发送温馨的告别，用中文回答。",
    tools=[say_goodbye],
)


# ==================== 根代理定义 ====================

weather_agent = LlmAgent(
    model=LiteLlm(model="dashscope/qwen-plus"),
    name="weather_agent",
    description=(
        "主协调代理，负责处理天气查询请求，并根据用户意图自动委派其他任务给子代理。"
        "你可以直接处理天气查询，也可以将问候和告别请求委派给专门的子代理。"
    ),
    instruction=(
        "你是主协调代理 weather_agent，具备以下能力："
        "1. 直接处理天气查询：使用 'get_weather_stateful' 工具查询城市天气，该工具会根据用户偏好自动调整温度单位"
        "2. 委派问候任务：当用户打招呼时，委派给 greeting_agent"
        "3. 委派告别任务：当用户说再见时，委派给 farewell_agent"
        "请根据用户意图选择合适的处理方式，用中文回答。"
    ),
    tools=[get_weather_stateful],
    sub_agents=[greeting_agent, farewell_agent],
    output_key="last_weather_report",
    before_model_callback=block_keyword_guardrail,
    before_tool_callback=block_paris_tool_guardrail,
)


# ==================== 运行配置 ====================

APP_NAME = "agent_team_app"
USER_ID = "user_1"
SESSION_ID = "session_001"

INITIAL_STATE = {
    "user:temperature_unit": "摄氏度",
}


async def create_session_with_state() -> tuple:
    session_service = InMemorySessionService()
    session = await session_service.create_session(
        app_name=APP_NAME,
        user_id=USER_ID,
        session_id=SESSION_ID,
        state=INITIAL_STATE
    )
    print(f"会话已创建: App='{APP_NAME}', User='{USER_ID}', Session='{SESSION_ID}'")
    print(f"初始状态: temperature_unit = {session.state.get('user:temperature_unit')}")
    return session_service, session


async def call_agent_async(query: str, runner: Runner, user_id: str, session_id: str, session_service: InMemorySessionService):
    """发送查询到 agent 并打印最终响应。"""
    print(f"\n>>> 用户查询: {query}")

    content = types.Content(role='user', parts=[types.Part(text=query)])

    final_response_text = "Agent 未生成最终响应。"

    async for event in runner.run_async(user_id=user_id, session_id=session_id, new_message=content):
        if event.is_final_response():
            if event.content and event.content.parts:
                final_response_text = event.content.parts[0].text
            elif event.actions and event.actions.escalate:
                final_response_text = f"Agent 升级: {event.error_message or '无具体消息。'}"
            break

    print(f"<<< Agent 响应: {final_response_text}")

    updated_session = await session_service.get_session(
        app_name=APP_NAME, user_id=user_id, session_id=session_id
    )
    last_report = updated_session.state.get("last_weather_report")
    if last_report:
        print(f"--- 状态已保存: last_weather_report = {last_report[:50]}..." if len(str(last_report)) > 50 else f"--- 状态已保存: last_weather_report = {last_report}")

    return final_response_text


async def run_conversation(runner: Runner, session_service: InMemorySessionService):
    """运行对话测试委托流程和状态感知功能。"""
    print("\n" + "=" * 60)
    print("测试 1: 天气查询（摄氏度）→ 验证状态感知工具")
    print("=" * 60)
    await call_agent_async("北京天气怎么样？", runner=runner, user_id=USER_ID, session_id=SESSION_ID, session_service=session_service)

    print("\n" + "=" * 60)
    print("测试 2: 问候请求 → 应委派给 greeting_agent")
    print("=" * 60)
    await call_agent_async("你好，我是小明", runner=runner, user_id=USER_ID, session_id=SESSION_ID, session_service=session_service)

    print("\n" + "=" * 60)
    print("测试 3: 切换温度单位偏好为华氏度")
    print("=" * 60)
    # ✅ 正确方式：直接修改 session_service.user_state
    # user:temperature_unit 中的 "temperature_unit" 存储在 user_state 中
    if APP_NAME not in session_service.user_state:
        session_service.user_state[APP_NAME] = {}
    if USER_ID not in session_service.user_state[APP_NAME]:
        session_service.user_state[APP_NAME][USER_ID] = {}
    session_service.user_state[APP_NAME][USER_ID]["temperature_unit"] = "华氏度"
    print(f"--- 温度单位已切换为: 华氏度（直接修改 user_state）")

    print("\n" + "=" * 60)
    print("测试 4: 天气查询（华氏度）→ 验证状态感知工具读取新偏好")
    print("=" * 60)
    await call_agent_async("上海天气怎么样？", runner=runner, user_id=USER_ID, session_id=SESSION_ID, session_service=session_service)

    print("\n" + "=" * 60)
    print("测试 5: 告别请求 → 应委派给 farewell_agent")
    print("=" * 60)
    await call_agent_async("我要走了，再见", runner=runner, user_id=USER_ID, session_id=SESSION_ID, session_service=session_service)

    print("\n" + "=" * 60)
    print("测试 6: 护栏测试 → 包含 BLOCK 关键词应被拦截")
    print("=" * 60)
    await call_agent_async("请帮我查询北京的天气，BLOCK", runner=runner, user_id=USER_ID, session_id=SESSION_ID, session_service=session_service)

    print("\n" + "=" * 60)
    print("测试 7: 护栏测试 → 正常请求应通过")
    print("=" * 60)
    await call_agent_async("深圳天气怎么样？", runner=runner, user_id=USER_ID, session_id=SESSION_ID, session_service=session_service)

    print("\n" + "=" * 60)
    print("测试 8: 工具护栏测试 → 查询巴黎天气应被拦截")
    print("=" * 60)
    await call_agent_async("巴黎天气怎么样？", runner=runner, user_id=USER_ID, session_id=SESSION_ID, session_service=session_service)

    print("\n" + "=" * 60)
    print("测试 9: 工具护栏测试 → 正常城市天气应通过（深圳）")
    print("=" * 60)
    await call_agent_async("深圳天气怎么样？", runner=runner, user_id=USER_ID, session_id=SESSION_ID, session_service=session_service)

    print("\n" + "=" * 60)
    print("最终会话状态检查")
    print("=" * 60)
    final_session = await session_service.get_session(app_name=APP_NAME, user_id=USER_ID, session_id=SESSION_ID)
    print(f"temperature_unit: {final_session.state.get('user:temperature_unit')}")
    print(f"last_weather_report: {final_session.state.get('last_weather_report')}")
    print(f"guardrail_block_keyword_triggered: {final_session.state.get('guardrail_block_keyword_triggered')}")
    print(f"guardrail_block_paris_triggered: {final_session.state.get('guardrail_block_paris_triggered')}")


async def main():
    print("=" * 60)
    print("Agent 团队启动（状态感知版本 + 护栏功能）")
    print("团队成员: weather_agent (根代理/协调者)")
    print("         ├── greeting_agent (问候子代理)")
    print("         └── farewell_agent (告别子代理)")
    print("状态功能: temperature_unit 用户偏好 + output_key 自动保存")
    print("模型护栏: block_keyword_guardrail 拦截包含 BLOCK 的请求")
    print("工具护栏: block_paris_tool_guardrail 拦截查询巴黎的请求")
    print("=" * 60)

    session_service, session = await create_session_with_state()

    runner = Runner(
        agent=weather_agent,
        app_name=APP_NAME,
        session_service=session_service
    )
    print(f"Runner 已创建，Agent: '{runner.agent.name}'")

    await run_conversation(runner, session_service)

    print("\n" + "=" * 50)
    print("对话结束")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
