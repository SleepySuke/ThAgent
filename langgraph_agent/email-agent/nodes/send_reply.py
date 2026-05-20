# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-17 14:46:45
@Description：
发送回复节点 — 通过 SMTP 发送最终回复邮件
'''

from langchain_core.runnables import RunnableConfig

from model.state import EmailAgentState
from utils.email_client import send_email


def send_reply_node(state: EmailAgentState, config: RunnableConfig | None = None) -> dict:
    """发送回复邮件"""
    cfg = config.get("configurable", {}) if config else {}

    draft = state.get("draft_response", "")
    sender = state.get("sender_email", "")
    subject = state.get("email_subject", "")

    if not draft or not sender:
        return {"send_status": "skipped: 无草稿或收件人"}

    try:
        send_email(
            smtp_server=cfg.get("smtp_server", "smtp.163.com"),
            email_address=cfg.get("email_address", ""),
            auth_code=cfg.get("auth_code", ""),
            to=sender,
            subject=f"Re: {subject}",
            body=draft,
        )
        return {"send_status": "sent"}
    except ConnectionError as e:
        return {"send_status": f"failed: {e}"}
