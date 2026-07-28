from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig

from model.state import EmailAgentState, EmailClassification
from agents.prompts import CLASSIFIER_SYSTEM


def _classify_node(state: EmailAgentState, config: RunnableConfig | None = None) -> dict:
    cfg = config.get("configurable", {}) if config else {}
    model = cfg.get("model")
    if not model:
        return {"classification": None}

    content = state.get("email_content", "")
    subject = state.get("email_subject", "")

    response = model.with_structured_output(EmailClassification).invoke([
        {"role": "system", "content": CLASSIFIER_SYSTEM},
        {"role": "user", "content": f"主题：{subject}\n正文：{content}"},
    ])
    return {"classification": response}


def create_classifier_subgraph():
    builder = StateGraph(EmailAgentState)
    builder.add_node("do_classify", _classify_node)
    builder.add_edge(START, "do_classify")
    builder.add_edge("do_classify", END)
    return builder.compile()
