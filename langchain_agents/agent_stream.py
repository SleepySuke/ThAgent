# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-03 01:16:33
@Description：
关于langchain中创建agent的方法，使用流式输出
'''
from langchain.agents import create_agent
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.tools import tool

@tool(description="获取天气信息的工具")
def get_weather(location: str) -> str:
    # 模拟获取天气信息的函数
    return f"{location}的天气晴朗，温度25摄氏度。"

@tool(description="获取城市信息的工具")
def get_city_info(city: str) -> str:
    # 模拟获取城市信息的函数
    return f"{city}是一个美丽的城市，拥有丰富的文化和历史。"

# 创建一个流式输出的agent
agent = create_agent(
    model=ChatTongyi(model="qwen-plus", api_key=''),
    tools=[get_weather, get_city_info],
    system_prompt="你是一个智能助手，可以回答用户的问题，并且可以使用工具来获取信息。需要告知思考过程，让我知道你为什么调用工具，以及工具的输入是什么。"
)
# 运行agent
for chunk in agent.stream(
    {
        'messages': [
            {"role": "user", "content": "请告诉我现在是星期几。"}
        ]

    },
    stream_mode="values"
):
    latest_msg = chunk['messages'][-1]
    if latest_msg.content:
        print(f"Agent: {latest_msg.content}")
    
    for tool_call in getattr(latest_msg, "tool_calls", []):
        print(f"Agent调用了工具: {tool_call['name']}，输入: {tool_call['args']}")
    
