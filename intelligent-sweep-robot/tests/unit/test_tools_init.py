# -*- coding: UTF-8 -*-
"""tools 包入口的单元测试。"""
import pytest

from tools import get_agent_tools
from tools.generate_external_data import generate_external_data
from tools.get_current_month import get_current_month
from tools.get_user_id import get_user_id


@pytest.fixture
def agent_tools():
    return get_agent_tools()


def test_get_agent_tools_returns_six_tools(agent_tools):
    """get_agent_tools 应该返回 6 个工具。"""
    assert len(agent_tools) == 6


def test_get_agent_tools_contains_all_expected_names(agent_tools):
    """返回的工具列表应该包含所有预定义的工具名称。"""
    names = {tool.name for tool in agent_tools}
    expected = {
        "rag_summarize",
        "get_weather",
        "get_user_location",
        "get_user_id",
        "get_current_month",
        "generate_external_data",
    }
    assert names == expected


def test_get_agent_tools_all_unique_instances(agent_tools):
    """返回的 6 个工具应该是 6 个不同的实例。"""
    ids = {id(tool) for tool in agent_tools}
    assert len(ids) == 6


def test_report_generation_tool_chain_format_compatible():
    """报告生成链中 get_user_id → get_current_month → generate_external_data 的输出格式应互相兼容。"""
    user_id = get_user_id.invoke({})
    month = get_current_month.invoke({})

    assert isinstance(user_id, str) and len(user_id) > 0
    assert isinstance(month, str) and len(month) == 7

    data = generate_external_data.invoke({"user_id": user_id, "month": month})

    assert user_id in data
    assert month in data
    assert "清洁次数" in data
