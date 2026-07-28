# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-17 13:26:22
@Description：
email agent的状态记录数据模型
'''

from typing import TypedDict, Annotated
from typing_extensions import Literal  # noqa: F811
from langgraph.graph.message import add_messages


class EmailClassification(TypedDict):
    """邮件分类意图识别内容"""
    intent: Literal["问题", "缺陷", "计费", "功能请求", "复杂"]
    urgency: Literal["low", "medium", "high", "critical"]
    confidence: float | None
    topic: str | None
    summary: str | None


class EmailAgentState(TypedDict):
    """email agent的状态记录内容"""
    email_id: str | None
    sender_email: str | None
    email_subject: str | None
    email_content: str | None
    classification: EmailClassification | None
    search_results: Annotated[list[str], lambda left, right: left + right]
    customer_history: dict | None
    draft_response: str | None
    review_status: Literal["approved", "needs_revision", "pending_draft"] | None
    send_status: str | None
    kb_results: list[dict] | None
    bug_results: list[dict] | None
    supervisor_decision: str | None
    supervisor_reasoning: str | None
    remaining_steps: int
    messages: Annotated[list, add_messages]
