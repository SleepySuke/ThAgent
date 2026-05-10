# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-08 23:41:18
@Description：
RAG 检索总结工具，为 Agent 提供知识库问答能力。
该工具是 Agent 的核心"手"之一，负责将用户问题转化为 RAG 查询，
并返回基于知识库资料的总结答案与来源。
'''
from langchain_core.tools import tool

from service.rag_service import RagSummarizeService

_rag_service: RagSummarizeService | None = None


def _get_rag_service() -> RagSummarizeService:
    """懒加载 RAG 服务单例，避免每次工具调用重复创建 Chroma 连接和 embedding 模型。"""
    global _rag_service
    if _rag_service is None:
        _rag_service = RagSummarizeService()
    return _rag_service


@tool
def rag_summarize(query: str) -> str:
    """从智扫通知识库检索产品资料、售前问答、售后排障、耗材维护、报告规则和示例模板，并生成基于资料的总结。"""
    result = _get_rag_service().query(query)
    sources = ", ".join(result.source_file_names) if result.source_file_names else "无"
    return f"答案：{result.answer}\n来源：{sources}"
