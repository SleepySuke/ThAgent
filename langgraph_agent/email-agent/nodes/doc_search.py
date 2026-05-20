# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-17 14:42:09
@Description：
文档检索节点 — 根据分类结果检索知识库，将结果写入 search_results
'''

from langchain_core.runnables import RunnableConfig

from model.state import EmailAgentState

SEARCH_PROMPT = """根据以下问题检索相关产品文档：
主题：{topic}
摘要：{summary}
邮件内容：{content}

请模拟知识库检索，列出3条最相关的文档条目。每条包含标题和简要说明。"""


def doc_search_node(state: EmailAgentState, config: RunnableConfig | None = None) -> dict:
    """根据分类 topic 检索知识库文档"""
    cfg = config.get("configurable", {}) if config else {}
    model = cfg.get("model")

    classification = state.get("classification") or {}
    topic = classification.get("topic", "")
    summary = classification.get("summary", "")

    if not model or not topic:
        return {"search_results": []}

    content = state.get("email_content", "")
    prompt = SEARCH_PROMPT.format(topic=topic, summary=summary, content=content[:2000])

    response = model.invoke(prompt)
    return {"search_results": [response.content]}
