# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-17 14:40:19
@Description：
意图识别节点 — 对邮件进行意图分类和紧急度评估
'''

from langchain_core.runnables import RunnableConfig

from model.state import EmailAgentState, EmailClassification

SYSTEM_PROMPT = """你是客服邮件分类专家。根据邮件内容输出分类结果。

意图 (intent)：
- 问题：用户遇到使用问题
- 缺陷：产品 bug 或故障
- 计费：账单、支付、退款相关
- 功能请求：新功能建议
- 复杂：多个类别混合或无法归类

紧急度 (urgency)：low / medium / high / critical
置信度 (confidence)：0.0 ~ 1.0，你对分类的把握程度
主题 (topic)：≤15字的简短概括
摘要 (summary)：一句话概括用户诉求"""


def classify_email_node(state: EmailAgentState, config: RunnableConfig | None = None) -> dict:
    """对邮件进行意图分类，结果写入 State"""
    cfg = config.get("configurable", {}) if config else {}

    content = state.get("email_content", "")
    subject = state.get("email_subject", "")

    model = cfg["model"]
    response = model.with_structured_output(EmailClassification).invoke([
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"主题：{subject}\n正文：{content}"},
    ])
    return {"classification": response}
