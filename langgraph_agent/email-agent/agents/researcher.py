from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage, ToolMessage

from model.state import EmailAgentState
from agents.react_utils import run_react_loop

RESEARCHER_PROMPT = """你是信息检索专家。根据邮件内容和分类结果，检索知识库和缺陷追踪系统。

## 工具

- search_kb(query): 搜索产品知识库（FAQ、产品文档、故障排查指南）
- query_bugs(keywords): 查询已知缺陷追踪系统

## 工作流程

1. 分析邮件的分类结果（intent/topic/summary）
2. 使用 search_kb 搜索相关文档
3. 如果分类意图是"缺陷"，额外使用 query_bugs 查询已知缺陷
4. 检索完成后，总结关键发现。如果没有找到相关内容，如实说明。

## 规则

- 必须至少调用一次 search_kb
- 检索结果要引用到具体的文档内容"""


def _researcher_node(state: EmailAgentState, config: RunnableConfig | None = None) -> dict:
    cfg = config.get("configurable", {}) if config else {}
    model = cfg.get("model")
    if not model:
        return {"search_results": ["[无法检索：模型不可用]"]}

    classification = state.get("classification") or {}
    context_parts = [
        f"邮件主题：{state.get('email_subject', 'N/A')}",
        f"邮件内容：{state.get('email_content', 'N/A')}",
    ]
    if classification:
        context_parts.append(
            f"分类结果：意图={classification.get('intent')}, "
            f"紧急度={classification.get('urgency')}, "
            f"主题={classification.get('topic')}, "
            f"摘要={classification.get('summary')}"
        )

    from tools.kb_search import search_kb
    from tools.bug_query import query_bugs

    def extract_results(messages: list) -> dict:
        """从 React 消息中提取检索结果"""
        results = []
        for msg in messages:
            if isinstance(msg, ToolMessage):
                results.append(str(msg.content))
        # 也从最后 AI 总结提取
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content:
                results.insert(0, f"[AI总结] {msg.content}")
                break
        return {"search_results": results}

    result = run_react_loop(
        model=model,
        tools=[search_kb, query_bugs],
        system_prompt=RESEARCHER_PROMPT,
        user_context="\n".join(context_parts),
        max_turns=4,
        result_extractor=extract_results,
    )
    return result


def create_researcher_agent(model):
    builder = StateGraph(EmailAgentState)
    builder.add_node("do_research", _researcher_node)
    builder.add_edge(START, "do_research")
    builder.add_edge("do_research", END)
    return builder.compile()
