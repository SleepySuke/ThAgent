# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-08 23:41:18
@Description：
用户 ID 查询工具，为 Agent 提供当前用户的唯一标识。
当前为 Mock 实现，用于学习阶段验证报告生成链路。
'''
from langchain_core.tools import tool


@tool
def get_user_id() -> str:
    """获取当前用户的唯一标识 ID，用于判断用户状态和生成个性化报告。"""
    return "user_001"
