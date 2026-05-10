# -*- coding: UTF-8 -*-
"""get_user_location 工具的单元测试。"""
from langchain_core.tools import BaseTool

from tools.get_user_location import get_user_location


def test_get_user_location_is_langchain_tool():
    """get_user_location 应该是 LangChain BaseTool 实例。"""
    assert isinstance(get_user_location, BaseTool)


def test_get_user_location_has_correct_name_and_description():
    """工具名称和描述应该准确。"""
    assert get_user_location.name == "get_user_location"
    assert "位置" in get_user_location.description or "城市" in get_user_location.description


def test_get_user_location_returns_shenzhen():
    """调用工具应该返回固定城市"深圳市"。"""
    result = get_user_location.invoke({})
    assert result == "深圳市"
