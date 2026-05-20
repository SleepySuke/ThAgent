# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-17
@Description：
条件边路由函数 — 根据 State 决定下一节点
'''

from model.state import EmailAgentState


def route_after_read_mail(state: EmailAgentState) -> str:
    """读取邮件后：有内容则继续分类，无内容则直接结束"""
    if state.get("email_content"):
        return "classify_email"
    return "end"


def route_after_classify(state: EmailAgentState) -> str:
    """分类后根据意图路由：doc_search / bug_tracking / human_review"""
    classification = state.get("classification")
    if classification is None:
        return "human_review"

    intent = classification.get("intent") or ""
    urgency = classification.get("urgency") or ""

    if intent == "缺陷":
        return "bug_tracking"
    if intent == "复杂" or urgency == "critical":
        return "human_review"
    return "doc_search"


def route_after_draft(state: EmailAgentState) -> str:
    """起草后始终进入人工审核，由人决定是否发送"""
    return "human_review"


def route_after_human_review(state: EmailAgentState) -> str:
    """人工审核后路由：
    - pending_draft（人工给出的处理意见）→ 去 draft_reply 生成正式草稿
    - needs_revision（打回）→ 重新起草
    - approved → 发送
    """
    review_status = state.get("review_status")
    if review_status in ("pending_draft", "needs_revision"):
        return "draft_reply"
    return "send_reply"
