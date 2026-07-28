import asyncio
import logging
from enum import Enum
import json

from langgraph.types import Command

logger = logging.getLogger(__name__)


class ReviewMode(Enum):
    CLI = "cli"
    WEB = "web"
    TUI = "tui"


async def process_email_with_hitl(
    graph, config: dict, initial_state: dict, mode: ReviewMode = ReviewMode.CLI,
) -> dict | None:
    """处理一封邮件，使用 astream 检测 HITL 中断。

    嵌套迭代模式：
    - 外层 while: 管理 interrupt/resume 生命周期
    - 内层 async for: 处理 graph.astream() 事件直到中断或完成
    """
    current_input = initial_state
    thread_id = config.get("configurable", {}).get("thread_id", "unknown")

    while True:
        interrupted = False
        interrupt_data = None

        try:
            async for event in graph.astream(
                current_input, config, stream_mode="updates"
            ):
                if "__interrupt__" in event:
                    interrupt_tuple = event["__interrupt__"]
                    interrupt_obj = interrupt_tuple[0]
                    interrupt_data = interrupt_obj.value
                    interrupted = True
                    break

                for node_name, node_output in event.items():
                    if node_name == "supervisor":
                        decision = node_output.get("supervisor_decision", "?")
                        logger.info("Supervisor → %s", decision)
                    elif node_name == "send_reply":
                        logger.info("Send: %s", node_output.get("send_status"))

        except Exception as e:
            logger.exception("Graph execution error")
            return None

        if not interrupted:
            state = await graph.aget_state(config)
            return state.values if state else None

        resume_value = await handle_interrupt(
            interrupt_data, mode=mode, thread_id=thread_id,
        )
        current_input = Command(resume=resume_value)


async def handle_interrupt(
    interrupt_data: dict,
    mode: ReviewMode = ReviewMode.CLI,
    thread_id: str | None = None,
) -> dict:
    """处理 HITL 中断，根据 mode 选择交互方式"""
    stage = interrupt_data.get("stage", "unknown")

    if mode == ReviewMode.WEB:
        return await _web_review(thread_id, interrupt_data)
    elif mode == ReviewMode.TUI:
        return await _tui_review(thread_id, interrupt_data)
    else:
        return await _cli_review(interrupt_data)


async def _cli_review(interrupt_data: dict) -> dict:
    """CLI 模式：input() 交互"""
    stage = interrupt_data.get("stage", "unknown")
    loop = asyncio.get_event_loop()

    if stage == "draft_review":
        _print_draft_review(interrupt_data)
        choice = (await loop.run_in_executor(None, input, "> ")).strip().lower()

        if choice == "r":
            reason = await loop.run_in_executor(None, input, "打回原因: ")
            return {"status": "needs_revision", "reason": reason}
        elif choice == "e":
            edited = await loop.run_in_executor(None, input, "修改后内容: ")
            return {"status": "approved", "edited_draft": edited}
        else:
            return {"status": "approved"}

    elif stage == "manual_process":
        _print_manual_process(interrupt_data)
        instruction = await loop.run_in_executor(None, input, "> ")
        return {"instruction": instruction}

    return {}


async def _web_review(thread_id: str | None, interrupt_data: dict) -> dict:
    """Web 模式：写入 review_queue，通过 asyncio.Event 等待 Web UI 决议"""
    if not thread_id:
        return {"status": "approved"}

    from persistence.review_repo import ReviewRepo
    from persistence.connection import get_pool

    pool = await get_pool()
    repo = ReviewRepo(pool)

    stage = interrupt_data.get("stage", "unknown")
    classification = interrupt_data.get("classification") or {}

    if stage == "draft_review":
        await repo.create(
            thread_id=thread_id,
            email_id="",
            sender_email=interrupt_data.get("sender", ""),
            email_subject=interrupt_data.get("subject", ""),
            draft_response=interrupt_data.get("draft", ""),
            classification=classification,
            interrupt_data=interrupt_data,
        )
        logger.info("Review created in DB: %s", thread_id)
        result = await repo.wait_for_resolution(thread_id)
        return {
            "status": "approved" if result.get("status") == "approved" else "needs_revision",
            "edited_draft": result.get("edited_draft", ""),
            "reason": result.get("comment", ""),
        }

    if stage == "manual_process":
        await repo.create(
            thread_id=thread_id,
            email_id="",
            sender_email=interrupt_data.get("sender", ""),
            email_subject=interrupt_data.get("subject", ""),
            draft_response="",
            classification={},
            interrupt_data=interrupt_data,
        )
        result = await repo.wait_for_resolution(thread_id)
        return {"instruction": result.get("comment", "")}

    return {}


async def _tui_review(thread_id: str | None, interrupt_data: dict) -> dict:
    """TUI 模式：通过 asyncio.Event 等待 Textual UI 决议（与 Web 共享 review_queue）"""
    return await _web_review(thread_id, interrupt_data)


def _print_draft_review(interrupt_data: dict):
    print("\n" + "=" * 60)
    print("⚠️  需要人工审核")
    print("=" * 60)
    print(f"发件人: {interrupt_data.get('sender', 'N/A')}")
    print(f"主题: {interrupt_data.get('subject', 'N/A')}")
    cls = interrupt_data.get("classification") or {}
    if cls:
        print(f"分类: {cls.get('intent')} / {cls.get('urgency')} / {cls.get('topic')}")
    print(f"\n草稿内容:\n{interrupt_data.get('draft', 'N/A')}")
    print("\n操作: [a]pprove 通过 / [r]evise 打回重写 / [e]dit 编辑后通过")


def _print_manual_process(interrupt_data: dict):
    print("\n" + "=" * 60)
    print("⚠️  复杂邮件需要人工处理")
    print("=" * 60)
    print(f"发件人: {interrupt_data.get('sender', 'N/A')}")
    content = interrupt_data.get("content", "")
    print(f"内容: {content[:500]}")
    print("\n请提供处理意见:")
