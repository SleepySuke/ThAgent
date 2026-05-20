# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-17 14:42:41
@Description：
缺陷追踪节点 — 查询已有缺陷记录，将结果写入 search_results
'''

from langchain_core.runnables import RunnableConfig

from model.state import EmailAgentState

BUG_TRACK_PROMPT = """查询以下用户反馈是否已有对应的缺陷记录：
邮件内容：{content}
分类：{intent} / {topic}

请列出相关的已有 issue（编号、标题、状态、严重级别），如没有则回复"无相关记录"。"""


def bug_tracking_node(state: EmailAgentState, config: RunnableConfig | None = None) -> dict:
    """查询缺陷追踪系统"""
    cfg = config.get("configurable", {}) if config else {}
    model = cfg.get("model")

    classification = state.get("classification") or {}
    intent = classification.get("intent", "")

    if not model or intent != "缺陷":
        return {"search_results": []}

    content = state.get("email_content", "")
    prompt = BUG_TRACK_PROMPT.format(
        content=content[:2000],
        intent=intent,
        topic=classification.get("topic", ""),
    )

    response = model.invoke(prompt)
    return {"search_results": [response.content]}
