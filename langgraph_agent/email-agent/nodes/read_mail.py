# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-17 14:07:18
@Description：
读取邮件节点 — 串联163邮箱客户端，获取未读邮件并写入State
'''

from langchain_core.runnables import RunnableConfig

from model.state import EmailAgentState
from utils.email_client import fetch_emails


def read_mail_node(state: EmailAgentState, config: RunnableConfig | None = None) -> dict:
    """读取163邮箱未读邮件，解析后写入 State。若 state 已有 email_content 则跳过（测试模式）。"""
    if state.get("email_content"):
        return {}

    cfg = config.get("configurable", {}) if config else {}

    emails = list(fetch_emails(
        imap_server=cfg.get("imap_server", "imap.163.com"),
        email_address=cfg.get("email_address"),
        auth_code=cfg.get("auth_code"),
    ))

    if not emails:
        return {}

    latest = emails[0]
    return {
        "email_id": latest["email_id"],
        "sender_email": latest["sender_email"],
        "email_subject": latest.get("email_subject"),
        "email_content": latest["email_content"],
    }
