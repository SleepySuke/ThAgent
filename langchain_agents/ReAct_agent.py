# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-03 18:13:06
@Description：
ReAct agent运作的范式
'''
from langchain.agents import create_agent
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.tools import tool

@tool(description="获取体重，返回值是整数，单位是千克")
def get_weight(name: str) -> int:
    # 模拟获取体重的函数
    return 70

@tool(description="获取身高，返回值是整数，单位是厘米")
def get_height(name: str) -> int:
    # 模拟获取身高的函数
    return 175

# 创建一个流式输出的agent
agent = create_agent(
    model=ChatTongyi(model="qwen-plus", api_key=''),
    tools=[get_weight, get_height],
    system_prompt="你是严格按照ReAct范式运作的智能助手，必须按照「思考-行动-观察」的流程解决问题，" \
    "且**每轮对话仅能思考并调用1个工具**，禁止单词调用多个工具"\
    "并且告知我，你的思考过程，工具调用的原因，按思考、行动、观察的格式输出告知我"
    
)
# 运行agent
for chunk in agent.stream(
    {
        'messages': [
            {"role": "user", "content": "计算我的BMI指数"}
        ]

    },
    stream_mode="values"
):
    latest_msg = chunk['messages'][-1]
    if latest_msg.content:
        print(latest_msg.content.strip())
    
    for tool_call in getattr(latest_msg, "tool_calls", []):
        print(f"Agent调用了工具: {tool_call['name']}，输入: {tool_call['args']}")
    
