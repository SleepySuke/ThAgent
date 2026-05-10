# -*- coding: UTF-8 -*-
"""generate_external_data 工具的单元测试。"""
from langchain_core.tools import BaseTool

from tools.generate_external_data import generate_external_data


def test_generate_external_data_is_langchain_tool():
    """generate_external_data 应该是 LangChain BaseTool 实例。"""
    assert isinstance(generate_external_data, BaseTool)


def test_generate_external_data_has_correct_name_and_description():
    """工具名称和描述应该准确。"""
    assert generate_external_data.name == "generate_external_data"
    assert "数据" in generate_external_data.description or "报告" in generate_external_data.description


def test_generate_external_data_args_schema_requires_user_id_and_month():
    """参数 schema 应该要求 user_id 和 month 字段。"""
    schema = generate_external_data.args_schema.model_json_schema()
    assert "user_id" in schema.get("required", [])
    assert "month" in schema.get("required", [])


def test_generate_external_data_returns_mock_data_with_inputs():
    """调用工具应该返回包含 user_id 和 month 的模拟数据。"""
    result = generate_external_data.invoke({"user_id": "user_123", "month": "2026-05"})
    assert isinstance(result, str)
    assert "user_123" in result
    assert "2026-05" in result


def test_generate_external_data_contains_all_expected_fields():
    """返回的模拟数据应包含清洁次数、面积、耗材状态和异常记录等关键字段。"""
    result = generate_external_data.invoke({"user_id": "u1", "month": "2026-05"})

    assert "清洁次数" in result
    assert "清洁面积" in result
    assert "主刷状态" in result
    assert "边刷状态" in result
    assert "滤网状态" in result
    assert "拖布状态" in result
    assert "异常记录" in result
