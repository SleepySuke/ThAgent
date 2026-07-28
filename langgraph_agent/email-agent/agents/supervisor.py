from typing import TypedDict
from typing_extensions import Literal

from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig

from model.state import EmailAgentState
from agents.prompts import build_supervisor_prompt


class RoutingDecision(TypedDict):
    next_agent: Literal[
        "classifier", "researcher", "draft_writer", "human_review", "end"
    ]
    reasoning: str


ROUTING_SYSTEM = """你是邮件处理 Supervisor。根据当前处理状态，输出下一步路由决策。

## 严格决策逻辑（按优先级）

1. 分类结果为"尚未分类" → next_agent = "classifier"
2. 已分类但信息检索为"未进行" → next_agent = "researcher"
3. 已完成检索但草稿为"未生成" → next_agent = "draft_writer"
4. 草稿已生成但审核状态为"未审核" → next_agent = "human_review"
5. 审核状态为"needs_revision"或"pending_draft" → next_agent = "draft_writer"
6. 审核状态为"approved" → next_agent = "end"

每次只输出一个决策。"""


def _supervisor_node(state: EmailAgentState, config: RunnableConfig | None = None) -> dict:
    cfg = config.get("configurable", {}) if config else {}
    model = cfg.get("model")
    if not model:
        return {"supervisor_decision": "end", "supervisor_reasoning": "model unavailable"}

    status_info = build_supervisor_prompt(state)
    prompt = f"{ROUTING_SYSTEM}\n\n{status_info}"

    response = model.with_structured_output(RoutingDecision).invoke([
        {"role": "system", "content": ROUTING_SYSTEM},
        {"role": "user", "content": status_info},
    ])
    return {
        "supervisor_decision": response.get("next_agent", "end"),
        "supervisor_reasoning": response.get("reasoning", ""),
    }


def create_supervisor_agent(model):
    builder = StateGraph(EmailAgentState)
    builder.add_node("do_route", _supervisor_node)
    builder.add_edge(START, "do_route")
    builder.add_edge("do_route", END)
    return builder.compile()
