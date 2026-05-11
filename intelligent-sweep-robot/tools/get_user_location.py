# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-08 23:41:18
@Description：
用户位置查询工具，为 Agent 提供当前用户所在城市信息。
当前为 Mock 实现，返回固定城市，用于学习阶段验证工具调用。
'''
from langchain_core.tools import tool


@tool(
    description="获取用户当前所在的城市或地理位置信息。当用户问题涉及天气、地理位置对拖地或烘干的影响，并且缺少地点信息时，先调用本工具获取城市，再按需调用 get_weather。"
)
def get_user_location() -> str:
    """获取用户当前所在的城市或地理位置信息。"""
    return "深圳市"
