# -*- coding: UTF-8 -*-
"""rag_summarize 工具的单元测试。"""
from unittest.mock import MagicMock, patch

from langchain_core.tools import BaseTool

from tools.rag_summarize import rag_summarize


def test_rag_summarize_is_langchain_tool():
    """rag_summarize 应该是 LangChain BaseTool 实例。"""
    assert isinstance(rag_summarize, BaseTool)


def test_rag_summarize_has_correct_name_and_description():
    """工具名称和描述应该准确，便于 LLM 识别调用时机。"""
    assert rag_summarize.name == "rag_summarize"
    assert "知识库" in rag_summarize.description
    assert "检索" in rag_summarize.description or "总结" in rag_summarize.description


def test_rag_summarize_args_schema_requires_query():
    """工具参数 schema 应该要求 query 字段。"""
    schema = rag_summarize.args_schema.model_json_schema()
    assert "query" in schema.get("required", [])
    assert "query" in schema.get("properties", {})


def test_rag_summarize_invokes_rag_service_and_returns_formatted_result():
    """调用工具时应该执行 RAG 查询并返回格式化的答案与来源。"""
    mock_result = MagicMock()
    mock_result.answer = "智扫通 S1 Max 支持自动集尘。"
    mock_result.source_file_names = ["03_model_s1_max_specs.txt"]

    with patch("tools.rag_summarize._rag_service") as mock_service:
        mock_service.query.return_value = mock_result
        result = rag_summarize.invoke({"query": "S1 Max 支持自动集尘吗？"})

    mock_service.query.assert_called_once_with("S1 Max 支持自动集尘吗？")
    assert "智扫通 S1 Max 支持自动集尘。" in result
    assert "03_model_s1_max_specs.txt" in result


def test_rag_summarize_handles_empty_source_file_names():
    """当知识库无匹配结果时，应使用"无"作为来源占位。"""
    mock_result = MagicMock()
    mock_result.answer = "当前知识库资料不足以确认该问题。"
    mock_result.source_file_names = []

    with patch("tools.rag_summarize._rag_service") as mock_service:
        mock_service.query.return_value = mock_result
        result = rag_summarize.invoke({"query": "不存在的产品功能？"})

    assert "当前知识库资料不足以确认该问题" in result
    assert "来源：无" in result
