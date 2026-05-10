# -*- coding: UTF-8 -*-
"""get_user_id 工具的单元测试。"""
from langchain_core.tools import BaseTool

from tools.get_user_id import get_user_id


def test_get_user_id_is_langchain_tool():
    """get_user_id 应该是 LangChain BaseTool 实例。"""
    assert isinstance(get_user_id, BaseTool)


def test_get_user_id_has_correct_name_and_description():
    """工具名称和描述应该准确。"""
    assert get_user_id.name == "get_user_id"
    assert "用户" in get_user_id.description or "ID" in get_user_id.description


def test_get_user_id_returns_fixed_id():
    """调用工具应该返回固定用户 ID "user_001"。"""
    result = get_user_id.invoke({})
    assert result == "user_001"
