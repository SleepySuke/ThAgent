# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-08 23:41:18
@Description：
当前月份查询工具，为 Agent 提供真实的时间参考。
该工具直接调用系统时间，是报告生成链路的关键输入之一。
'''
from datetime import datetime

from langchain_core.tools import tool


@tool(
    description="获取当前月份（格式 YYYY-MM），用于生成月度报告或判断时间范围。当用户说'本月''这个月''月度报告'等时间范围，且没有指定具体月份时调用。"
)
def get_current_month() -> str:
    """获取当前月份，用于生成月度报告或判断时间范围。"""
    return datetime.now().strftime("%Y-%m")
