# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-17 14:45:51
@Description：
起草回复节点 — LLM 根据分类和检索结果生成回复草稿
'''

from langchain_core.runnables import RunnableConfig

from model.state import EmailAgentState

DRAFT_SYSTEM = """你是专业的客服邮件回复助手。根据用户邮件和相关背景信息，起草一封回复。

要求：
1. 语气专业、友善、具体
2. 针对用户问题给出实质性回复
3. 如检索到相关文档，引用关键信息
4. 如涉及缺陷，告知用户当前处理状态
5. 署名：客服团队"""


def draft_reply_node(state: EmailAgentState, config: RunnableConfig | None = None) -> dict:
    """根据分类和检索结果生成回复草稿"""
    cfg = config.get("configurable", {}) if config else {}
    model = cfg.get("model")
    if not model:
        return {"draft_response": "[无法生成草稿：模型不可用]"}

    content = state.get("email_content", "")
    subject = state.get("email_subject", "")
    sender = state.get("sender_email", "")
    classification = state.get("classification") or {}
    search_results = state.get("search_results") or []
    review_status = state.get("review_status")
    existing_draft = state.get("draft_response", "")

    # pending_draft → 人工处理意见，作为草稿依据
    if review_status == "pending_draft" and existing_draft:
        context_parts = [
            f"发件人：{sender}",
            f"主题：{subject}",
            f"原始邮件：{content}",
            f"人工处理意见（请据此起草正式回复）：{existing_draft}",
        ]
    elif review_status == "needs_revision" and existing_draft:
        context_parts = [
            f"发件人：{sender}",
            f"主题：{subject}",
            f"原始邮件：{content}",
            f"上一版草稿（被打回）：{existing_draft}",
            "请根据以上信息重新起草回复。",
        ]
    else:
        intent = classification.get("intent") or "一般咨询"
        urgency = classification.get("urgency") or "常规"
        topic = classification.get("topic") or (subject or "未分类")
        summary = classification.get("summary") or ""

        context_parts = [
            f"发件人：{sender}",
            f"主题：{subject}",
            f"原始邮件：{content}",
            f"分类结果 — 意图：{intent} | 紧急度：{urgency} | 主题：{topic}",
        ]
        if summary:
            context_parts.append(f"摘要：{summary}")
        if search_results:
            context_parts.append(f"检索结果：{search_results[0]}")

    prompt = "\n\n".join(context_parts)

    response = model.invoke([
        {"role": "system", "content": DRAFT_SYSTEM},
        {"role": "user", "content": prompt},
    ])
    return {"draft_response": response.content}
