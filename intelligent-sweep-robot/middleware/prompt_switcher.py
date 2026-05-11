# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-11
@Description：
Prompt 动态切换 Middleware。

使用 LangChain dynamic_prompt 装饰器，在每次 Agent 节点执行时
根据用户消息动态选择 system prompt（main / report）。

调用方式：
    from middleware.prompt_switcher import build_prompt_middleware
    mw = build_prompt_middleware(bundle)
    agent = create_agent(model=model, tools=tools, middleware=[mw, ...])
'''
from langchain.agents.middleware import dynamic_prompt

from utils.prompt_handler import PromptBundle

_REPORT_KEYWORDS = {"报告", "月度", "清洁分析", "使用建议", "使用报告", "月度报告"}


def build_prompt_middleware(bundle: PromptBundle):
    """构建动态 prompt 切换 middleware。

    每次模型调用前根据 state 中最后一条 human 消息匹配关键词：
    - 命中报告关键词 → report_prompt
    - 其他 → main_prompt

    rag_prompt 不在此处切换——它由 RagSummarizeService 内部使用。
    """

    @dynamic_prompt
    def _select_prompt(request):
        messages = request.state.get("messages", [])
        user_content = ""
        for msg in reversed(messages):
            msg_type = getattr(msg, "type", None)
            if msg_type == "human":
                user_content = getattr(msg, "content", "")
                break

        if any(kw in user_content for kw in _REPORT_KEYWORDS):
            return bundle.report_prompt.content
        return bundle.main_prompt.content

    return _select_prompt
