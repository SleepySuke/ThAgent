from langgraph.graph import StateGraph, START, END
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import AIMessage, ToolMessage

from model.state import EmailAgentState
from agents.react_utils import run_react_loop

DRAFT_PROMPT = """你是专业的客服邮件回复撰写专家。根据邮件内容、分类结果和检索信息，撰写回复草稿。

## 工具

- write_draft(subject, body): 保存草稿。subject 是邮件主题（不含 Re: 前缀），body 是完整正文。
- revise_draft(feedback, current_draft): 根据反馈修改已有的草稿。

## 工作流程

1. 分析原始邮件和分类结果，理解用户诉求
2. 参考检索结果中的文档内容（如有），引用关键信息
3. 使用 write_draft 工具保存完整草稿。必须调用这个工具，不要只输出文本。
4. 如果这是修订请求（有 feedback），使用 revise_draft 工具

## 草稿要求

1. 语气专业、友善、具体
2. 直接回答用户问题，不要含糊
3. 如果检索到相关文档，引用关键信息
4. 如果涉及已知缺陷，告知当前处理状态和临时方案
5. 署名：客服团队"""


def _draft_node(state: EmailAgentState, config: RunnableConfig | None = None) -> dict:
    cfg = config.get("configurable", {}) if config else {}
    model = cfg.get("model")
    if not model:
        return {"draft_response": "[无法生成草稿：模型不可用]"}

    classification = state.get("classification") or {}
    search_results = state.get("search_results") or []
    review_status = state.get("review_status")
    existing_draft = state.get("draft_response", "")

    context_parts = [
        f"发件人：{state.get('sender_email', '')}",
        f"主题：{state.get('email_subject', '')}",
        f"原始邮件：{state.get('email_content', '')}",
    ]
    if classification:
        context_parts.append(
            f"分类 — 意图：{classification.get('intent')} | "
            f"紧急度：{classification.get('urgency')} | "
            f"主题：{classification.get('topic')}"
        )
    if review_status == "needs_revision" and existing_draft:
        context_parts.append(f"上一版草稿被打回，需要重新起草。原草稿：{existing_draft}")
    if search_results:
        for r in search_results[:3]:
            context_parts.append(f"检索结果：{r[:800]}")

    from tools.draft_tools import write_draft, revise_draft

    def extract_draft(messages: list) -> dict:
        """从 React 消息中提取草稿"""
        # 先找 write_draft 工具调用结果
        for msg in messages:
            if isinstance(msg, ToolMessage) and "DRAFT_SAVED" in str(msg.content):
                # 格式: DRAFT_SAVED::SUBJECT::xxx::BODY::yyy
                parts = str(msg.content).split("::")
                if len(parts) >= 5:
                    return {"draft_response": parts[4]}
        # 退而求其次，取最后 AI 消息
        for msg in reversed(messages):
            if isinstance(msg, AIMessage) and msg.content and "DRAFT_SAVED" not in str(msg.content):
                return {"draft_response": str(msg.content)}
        return {"draft_response": "[草稿生成失败]"}

    result = run_react_loop(
        model=model,
        tools=[write_draft, revise_draft],
        system_prompt=DRAFT_PROMPT,
        user_context="\n".join(context_parts),
        max_turns=4,
        result_extractor=extract_draft,
    )
    return result


def create_draft_writer_agent(model):
    builder = StateGraph(EmailAgentState)
    builder.add_node("do_draft", _draft_node)
    builder.add_edge(START, "do_draft")
    builder.add_edge("do_draft", END)
    return builder.compile()
