from model.state import EmailAgentState


def route_after_supervisor(state: EmailAgentState) -> str:
    """根据 supervisor_decision 路由到目标节点"""
    decision = state.get("supervisor_decision", "end")
    valid = {"classifier", "researcher", "draft_writer", "human_review", "end"}
    return decision if decision in valid else "end"


def route_after_read_mail(state: EmailAgentState) -> str:
    """读取邮件后：有内容则继续，无内容则直接结束"""
    if state.get("email_content"):
        return "supervisor"
    return "end"


def route_after_human_review(state: EmailAgentState) -> str:
    """人工审核后路由：
    - pending_draft / needs_revision → draft_writer 重新起草
    - approved → send_reply
    """
    review_status = state.get("review_status")
    if review_status in ("pending_draft", "needs_revision"):
        return "draft_writer"
    return "send_reply"
