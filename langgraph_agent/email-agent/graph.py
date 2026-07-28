from langgraph.graph import StateGraph, START, END

from model.state import EmailAgentState
from nodes.read_mail import read_mail_node
from nodes.human_review import human_review_node
from nodes.send_reply import send_reply_node
from edges import (
    route_after_supervisor,
    route_after_read_mail,
    route_after_human_review,
)


def build_multi_agent_graph(model):
    """构建 multi-agent 邮件处理图。

    Topology:
        START → read_mail → supervisor → specialist → ...
        Specialists (classifier, researcher) return to supervisor.
        draft_writer → human_review → (draft_writer loop | send_reply → END)
    """
    from agents.supervisor import create_supervisor_agent
    from agents.classifier import create_classifier_subgraph
    from agents.researcher import create_researcher_agent
    from agents.draft_writer import create_draft_writer_agent

    supervisor = create_supervisor_agent(model)
    classifier = create_classifier_subgraph()
    researcher = create_researcher_agent(model)
    draft_writer = create_draft_writer_agent(model)

    graph = StateGraph(EmailAgentState)

    graph.add_node("read_mail", read_mail_node)
    graph.add_node("supervisor", supervisor)
    graph.add_node("classifier", classifier)
    graph.add_node("researcher", researcher)
    graph.add_node("draft_writer", draft_writer)
    graph.add_node("human_review", human_review_node)
    graph.add_node("send_reply", send_reply_node)

    graph.add_edge(START, "read_mail")

    graph.add_conditional_edges(
        "read_mail", route_after_read_mail,
        {"supervisor": "supervisor", "end": END},
    )

    graph.add_conditional_edges(
        "supervisor", route_after_supervisor,
        {
            "classifier": "classifier",
            "researcher": "researcher",
            "draft_writer": "draft_writer",
            "human_review": "human_review",
            "end": END,
        },
    )

    graph.add_edge("classifier", "supervisor")
    graph.add_edge("researcher", "supervisor")

    graph.add_edge("draft_writer", "human_review")

    graph.add_conditional_edges(
        "human_review", route_after_human_review,
        {"draft_writer": "draft_writer", "send_reply": "send_reply"},
    )

    graph.add_edge("send_reply", END)

    return graph
