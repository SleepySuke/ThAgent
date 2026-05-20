# -*- coding: UTF-8 -*-
'''
@Author ：suke
@Version ：1.0
@Date ：2026-05-17 13:44:40
@Description：
email-agent 入口 — 加载配置、创建模型、编译图、执行完整流程
'''

import os
import sys
import json

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from model.llm import create_model
from graph import build_email_agent_graph
from utils.config_handler import load_project_config


def _build_graph(model):
    """构建并编译带检查点的图"""
    checkpointer = InMemorySaver()
    builder = build_email_agent_graph()
    return builder.compile(checkpointer=checkpointer)


def _make_config(model, thread_id: str = "email-1") -> dict:
    """构造运行时 config"""
    return {
        "configurable": {
            "thread_id": thread_id,
            "model": model,
            "imap_server": os.getenv("IMAP_SERVER", "imap.163.com"),
            "smtp_server": os.getenv("SMTP_SERVER", "smtp.163.com"),
            "email_address": os.getenv("EMAIL_ADDRESS", ""),
            "auth_code": os.getenv("EMAIL_AUTH_CODE", ""),
        }
    }


def run_email_agent(thread_id: str = "email-1", test_mode: bool = False):
    """执行 email agent 完整流程，处理人工审核中断"""
    project_config = load_project_config()
    model = create_model(project_config)
    graph = _build_graph(model)
    config = _make_config(model, thread_id)

    if test_mode:
        initial_state = {
            "email_id": "test-1",
            "sender_email": "test@example.com",
            "email_subject": "兰州天气咨询",
            "email_content": "请问兰州明天天气怎么样？我计划去旅游，想知道需要带什么衣服。",
        }
        result = _run_with_interrupt(graph, config, initial_state)
        if result:
            print(json.dumps(_summarize(result), ensure_ascii=False, indent=2))
        return result

    initial_state = {}
    result = _run_with_interrupt(graph, config, initial_state)
    if result:
        print(json.dumps(_summarize(result), ensure_ascii=False, indent=2))


def _run_with_interrupt(graph, config, initial_state):
    """执行图并循环处理中断，直到流程结束"""
    result = graph.invoke(initial_state, config)

    if not initial_state and result is None:
        print("没有新邮件")
        return None

    while True:
        state = graph.get_state(config)
        if not state.interrupts:
            return result

        interrupt_data = state.interrupts[0].value
        _handle_interrupt(graph, config, interrupt_data)

        # 继续执行剩余流程
        result = graph.get_state(config).values

    return result


def _handle_interrupt(graph, config, interrupt_data: dict):
    """处理人工审核中断 — 交互式审批"""
    print("\n" + "=" * 60)
    print("⚠️  需要人工审核")
    print("=" * 60)

    stage = interrupt_data.get("stage", "unknown")
    if stage == "draft_review":
        print(f"发件人: {interrupt_data.get('sender', 'N/A')}")
        print(f"主题: {interrupt_data.get('subject', 'N/A')}")
        print(f"\n草稿内容:\n{interrupt_data.get('draft', 'N/A')}")
        print("\n操作: [a]pprove 通过 / [r]evise 打回重写 / [e]dit 编辑后通过")
        choice = input("> ").strip().lower()

        if choice == "r":
            reason = input("打回原因: ")
            graph.invoke(Command(resume={"status": "needs_revision", "reason": reason}), config)
        elif choice == "e":
            edited = input("修改后内容: ")
            graph.invoke(Command(resume={"status": "approved", "edited_draft": edited}), config)
        else:
            graph.invoke(Command(resume={"status": "approved"}), config)
    elif stage == "manual_process":
        print(f"发件人: {interrupt_data.get('sender', 'N/A')}")
        print(f"内容: {interrupt_data.get('content', 'N/A')[:500]}")
        print("\n请提供处理意见:")
        instruction = input("> ")
        graph.invoke(Command(resume={"instruction": instruction}), config)

    print("✓ 审核完成，继续执行...\n")


def _summarize(state: dict) -> dict:
    """提取关键字段用于输出"""
    classification = state.get("classification") or {}
    return {
        "email_id": state.get("email_id"),
        "sender_email": state.get("sender_email"),
        "subject": state.get("email_subject"),
        "intent": classification.get("intent"),
        "urgency": classification.get("urgency"),
        "topic": classification.get("topic"),
        "confidence": classification.get("confidence"),
        "draft_response": state.get("draft_response", "")[:200],
        "review_status": state.get("review_status"),
        "send_status": state.get("send_status"),
    }


if __name__ == "__main__":
    test_mode = "--test" in sys.argv
    args = [a for a in sys.argv[1:] if a != "--test"]
    thread_id = args[0] if args else "email-1"
    run_email_agent(thread_id, test_mode=test_mode)
