# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-08 23:41:18
@Description：
智扫通 Agent 工具包入口。
集中管理所有可供 LLM 调用的工具，是 Agent "手脚"能力的统一暴露层。
'''
from tools.generate_external_data import generate_external_data
from tools.get_current_month import get_current_month
from tools.get_user_id import get_user_id
from tools.get_user_location import get_user_location
from tools.get_weather import get_weather
from tools.rag_summarize import rag_summarize


def get_agent_tools():
    """返回 Agent 可用的全部工具列表。"""
    return [
        rag_summarize,
        get_weather,
        get_user_location,
        get_user_id,
        get_current_month,
        generate_external_data,
    ]
