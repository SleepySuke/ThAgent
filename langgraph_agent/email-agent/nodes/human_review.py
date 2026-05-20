# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-17 14:43:30
@Description：
HITL人工审核节点 — 暂停等人工审批，通过后继续或打回重拟
'''

from langchain_core.runnables import RunnableConfig
from langgraph.types import interrupt

from model.state import EmailAgentState


def human_review_node(state: EmailAgentState, config: RunnableConfig | None = None) -> dict:
    """人工审核：暂停执行，等待人工输入 approval 或 revision 决定"""
    draft = state.get("draft_response", "")
    has_draft = bool(draft)

    # 基于不同阶段构造中断信息
    if has_draft:
        # 审核草稿阶段
        decision = interrupt({
            "stage": "draft_review",
            "subject": state.get("email_subject"),
            "sender": state.get("sender_email"),
            "classification": state.get("classification"),
            "draft": draft,
        })
        return {
            "review_status": decision.get("status", "approved"),
            "draft_response": decision.get("edited_draft", draft),
        }

    # 分类直连阶段（复杂邮件，无草稿）—— 人工给出处理意见
    note = interrupt({
        "stage": "manual_process",
        "subject": state.get("email_subject"),
        "sender": state.get("sender_email"),
        "content": state.get("email_content"),
        "classification": state.get("classification"),
        "hint": "请提供处理意见，将作为 draft 依据",
    })

    return {
        "review_status": "pending_draft",
        "draft_response": note.get("instruction", ""),
    }
