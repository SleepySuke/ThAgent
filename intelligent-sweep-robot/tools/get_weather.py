# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-08 23:41:18
@Description：
天气查询工具，为 Agent 提供指定地点的天气信息。
当前为 Mock 实现，用于学习阶段验证 Agent 的工具调用链路。
后续可替换为真实天气 API。
'''
from langchain_core.tools import tool


@tool
def get_weather(city: str) -> str:
    """获取指定地点的当前天气信息，包括温度、湿度、降雨概率等。"""
    return f"{city}当前天气：晴，25°C，湿度60%，降雨概率10%，适合拖地。"
