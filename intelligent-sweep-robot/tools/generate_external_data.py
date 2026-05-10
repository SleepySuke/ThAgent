# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-08 23:41:18
@Description：
外部设备使用数据生成工具，为 Agent 提供扫地机器人的模拟使用数据。
当前为 Mock 实现，根据 user_id 和 month 返回固定格式的模拟数据，
用于验证报告生成链路，后续可对接真实设备数据平台。
'''
from langchain_core.tools import tool


@tool
def generate_external_data(user_id: str, month: str) -> str:
    """根据用户 ID 和月份生成扫地机器人使用数据，包括清洁次数、清洁面积、耗材状态和异常日志。"""
    return (
        f"用户 {user_id} {month} 使用数据：\n"
        "- 清洁次数：12次\n"
        "- 清洁面积：320平方米\n"
        "- 主刷状态：良好（剩余寿命80%）\n"
        "- 边刷状态：需更换（剩余寿命15%）\n"
        "- 滤网状态：良好（剩余寿命70%）\n"
        "- 拖布状态：一般（剩余寿命40%）\n"
        "- 异常记录：无"
    )
