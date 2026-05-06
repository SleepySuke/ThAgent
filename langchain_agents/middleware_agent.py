# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-03 18:23:42
@Description：
agent中间件--middleware
'''

from langchain.agents import create_agent,AgentState
from langchain.agents.middleware import ModelRequest
from langchain_community.chat_models.tongyi import ChatTongyi
from langchain_core.tools import tool
from langchain.agents.middleware import before_agent,after_agent,before_model,after_model,wrap_model_call,wrap_tool_call
from langgraph.runtime import Runtime



@tool(description="获取天气信息的工具")
def get_weather(location: str) -> str:
    # 模拟获取天气信息的函数
    return f"{location}的天气晴朗，温度25摄氏度。"

'''
1.agent执行前
2.agent执行后
3.model调用前
4.model调用后
5.工具调用中
6.model执行中
'''

@before_agent
def log_before_agent(state: AgentState,runtime: Runtime) -> None:
    '''
    在agent执行前记录日志
    '''
    print("Agent即将执行，当前状态:", state)

@after_agent
def log_after_agent(state: AgentState,runtime: Runtime) -> None:
    '''
    在agent执行后记录日志
    '''
    print("Agent执行完成，当前状态:", state)

@before_model
def log_before_model(state: AgentState,runtime: Runtime) -> None:
    '''
    在model调用前记录日志
    '''
    print(f"即将调用模型，当前消息数量: {len(state['messages'])}")

@after_model
def log_after_model(state: AgentState,runtime: Runtime) -> None:
    '''
    在model调用后记录日志
    '''
    latest_message = state["messages"][-1]
    print(f"模型调用完成，最新消息: {latest_message}")

@wrap_tool_call
def log_tool_call(request, handler):
    '''
    在工具调用中记录日志
    '''
    tool_name = request.tool_call["name"]
    tool_args = request.tool_call["args"]
    print(f"即将调用工具: {tool_name}，输入: {tool_args}")
    result = handler(request)
    print(f"工具调用完成: {tool_name}，输出: {result}")
    return result

@wrap_model_call
def log_model_call(request: ModelRequest, handler):
    '''
    在模型调用中记录日志
    '''
    model_name = getattr(request.model, "model", request.model.__class__.__name__)
    print(f"即将调用模型: {model_name}，输入消息数量: {len(request.messages)}")
    result = handler(request)
    print(f"模型调用完成: {model_name}，输出: {result}")
    return result

# 创建一个流式输出的agent
agent = create_agent(
    model=ChatTongyi(model="qwen-plus", api_key=''),
    tools=[get_weather],
    middleware=[log_before_agent, log_after_agent, log_before_model, log_after_model, log_tool_call, log_model_call],
    system_prompt="你是一个智能助手，可以回答用户的问题，并且可以使用工具来获取信息。需要告知思考过程，让我知道你为什么调用工具，以及工具的输入是什么。"
)
# 运行agent
for chunk in agent.stream(
    {
        'messages': [
            {"role": "user", "content": "请告诉北京现在的天气。"}
        ]

    },
    stream_mode="values"
):
    latest_msg = chunk['messages'][-1]
    if latest_msg.content:
        print(f"Agent: {latest_msg.content}")
    
    for tool_call in getattr(latest_msg, "tool_calls", []):
        print(f"Agent调用了工具: {tool_call['name']}，输入: {tool_call['args']}")
