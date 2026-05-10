# -*- coding: UTF-8 -*-
"""get_weather 工具的单元测试。"""
from langchain_core.tools import BaseTool

from tools.get_weather import get_weather


def test_get_weather_is_langchain_tool():
    """get_weather 应该是 LangChain BaseTool 实例。"""
    assert isinstance(get_weather, BaseTool)


def test_get_weather_has_correct_name_and_description():
    """工具名称和描述应该准确。"""
    assert get_weather.name == "get_weather"
    assert "天气" in get_weather.description


def test_get_weather_args_schema_requires_city():
    """参数 schema 应该要求 city 字段。"""
    schema = get_weather.args_schema.model_json_schema()
    assert "city" in schema.get("required", [])


def test_get_weather_returns_mock_data_containing_city():
    """调用工具应该返回包含城市名的模拟天气数据。"""
    result = get_weather.invoke({"city": "北京"})
    assert "北京" in result
    assert isinstance(result, str)
