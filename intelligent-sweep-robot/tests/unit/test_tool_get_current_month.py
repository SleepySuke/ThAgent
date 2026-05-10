# -*- coding: UTF-8 -*-
"""get_current_month 工具的单元测试。"""
from datetime import datetime

from langchain_core.tools import BaseTool

from tools.get_current_month import get_current_month


def test_get_current_month_is_langchain_tool():
    """get_current_month 应该是 LangChain BaseTool 实例。"""
    assert isinstance(get_current_month, BaseTool)


def test_get_current_month_has_correct_name_and_description():
    """工具名称和描述应该准确。"""
    assert get_current_month.name == "get_current_month"
    assert "月份" in get_current_month.description or "月" in get_current_month.description


def test_get_current_month_returns_valid_format():
    """返回格式应为 YYYY-MM。"""
    result = get_current_month.invoke({})
    assert isinstance(result, str)
    # 验证格式
    parsed = datetime.strptime(result, "%Y-%m")
    assert parsed.year == datetime.now().year
    assert parsed.month == datetime.now().month
