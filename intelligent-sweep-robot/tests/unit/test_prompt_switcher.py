# -*- coding: UTF-8 -*-
"""middleware.prompt_switcher 单元测试。"""
from unittest.mock import MagicMock

from langchain.agents.middleware import ModelRequest

from middleware.prompt_switcher import build_prompt_middleware


def _call_dynamic_prompt(mw, human_content):
    """通过 wrap_model_call 触发 dynamic_prompt 中间件。"""
    model = MagicMock()
    msg = MagicMock(type="human", content=human_content)
    state = {"messages": [msg]}
    runtime = MagicMock()
    request = ModelRequest(
        model=model,
        messages=[msg],
        state=state,
        runtime=runtime,
    )

    def handler(r):
        return r

    result = mw.wrap_model_call(request, handler)
    return result.system_prompt


def test_selects_report_for_report_keywords():
    """当用户消息包含报告关键词时，应返回 report_prompt。"""
    bundle = MagicMock()
    bundle.main_prompt.content = "main"
    bundle.report_prompt.content = "report content"

    mw = build_prompt_middleware(bundle)
    result = _call_dynamic_prompt(mw, "帮我生成本月报告")

    assert str(result) == "report content"


def test_defaults_to_main():
    """当无匹配关键词时，应返回 main_prompt。"""
    bundle = MagicMock()
    bundle.main_prompt.content = "main content"
    bundle.report_prompt.content = "report content"

    mw = build_prompt_middleware(bundle)
    result = _call_dynamic_prompt(mw, "你好")

    assert str(result) == "main content"


def test_non_report_query_returns_main():
    """非报告类查询（如产品咨询）应返回 main_prompt。"""
    bundle = MagicMock()
    bundle.main_prompt.content = "main content"
    bundle.report_prompt.content = "report content"

    mw = build_prompt_middleware(bundle)
    result = _call_dynamic_prompt(mw, "S1支持自动集尘吗")

    assert str(result) == "main content"
