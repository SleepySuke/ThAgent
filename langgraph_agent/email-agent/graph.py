# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-17 13:46:46
@Description：
构建 email agent 状态流转图
'''

from langgraph.graph import StateGraph, START, END

from model.state import EmailAgentState
from nodes.read_mail import read_mail_node
from nodes.classify_email import classify_email_node
from nodes.doc_search import doc_search_node
from nodes.bug_tracking import bug_tracking_node
from nodes.draft_reply import draft_reply_node
from nodes.human_review import human_review_node
from nodes.send_reply import send_reply_node
from edges import (
    route_after_read_mail,
    route_after_classify,
    route_after_human_review,
)


def build_email_agent_graph() -> StateGraph:
    """构建 email agent 状态流转图"""
    graph = StateGraph(EmailAgentState)

    # ── nodes ──
    graph.add_node("read_mail", read_mail_node)
    graph.add_node("classify_email", classify_email_node)
    graph.add_node("doc_search", doc_search_node)
    graph.add_node("bug_tracking", bug_tracking_node)
    graph.add_node("draft_reply", draft_reply_node)
    graph.add_node("human_review", human_review_node)
    graph.add_node("send_reply", send_reply_node)

    # ── edges ──
    graph.add_edge(START, "read_mail")

    graph.add_conditional_edges(
        "read_mail", route_after_read_mail,
        {"classify_email": "classify_email", "end": END},
    )

    graph.add_conditional_edges(
        "classify_email", route_after_classify,
        {"doc_search": "doc_search", "bug_tracking": "bug_tracking", "human_review": "human_review"},
    )

    graph.add_edge("doc_search", "draft_reply")
    graph.add_edge("bug_tracking", "draft_reply")

    graph.add_edge("draft_reply", "human_review")

    graph.add_conditional_edges(
        "human_review", route_after_human_review,
        {"draft_reply": "draft_reply", "send_reply": "send_reply"},
    )

    graph.add_edge("send_reply", END)

    return graph
