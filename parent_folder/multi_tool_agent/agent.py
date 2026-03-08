# -*- coding: UTF-8 -*-
'''
@Author ：自然醒
@Version ：1.0
'''
import datetime
from zoneinfo import ZoneInfo
from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm
from dotenv import load_dotenv

load_dotenv()

def get_weather(city: str) -> dict:
    """获取指定城市的当前天气报告。

    Args:
        city (str): 要获取天气报告的城市名称。

    Returns:
        dict: 状态和结果或错误信息。
    """
    return {
        "status": "success",
        "report": f"{city}今天天气晴朗，气温适宜，适合户外活动。",
    }


def get_current_time(city: str) -> dict:
    """返回指定城市的当前时间。

    Args:
        city (str): 要获取当前时间的城市名称。

    Returns:
        dict: 状态和结果或错误信息。
    """
    tz = ZoneInfo("Asia/Shanghai")
    now = datetime.datetime.now(tz)
    report = f'{city}的当前时间是 {now.strftime("%Y-%m-%d %H:%M:%S")}'
    return {"status": "success", "report": report}


root_agent = LlmAgent(
    model=LiteLlm("dashscope/qwen-plus"),
    name="weather_time_agent",
    description="回答中国城市时间和天气问题的智能助手。",
    instruction=(
        "你是一个专注于中国城市信息查询的智能助手。"
        "你的职责是帮助用户查询中国大陆城市的时间和天气信息。"
        "当用户询问某个城市的时间或天气时，请调用相应的工具函数。"
        "所有城市均使用中国标准时间（北京时间，UTC+8）。"
        "请始终使用中文与用户交流。"
    ),
    tools=[get_weather, get_current_time],
)
