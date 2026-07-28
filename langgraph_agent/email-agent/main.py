"""
email-agent 入口 — 四种运行模式:
  python main.py --test     单封测试 + CLI 审批
  python main.py --web      FastAPI Web 界面 (http://localhost:8000)
  python main.py --tui      Textual 终端界面
  python main.py --daemon   后台 agent-loop 无 UI
"""

import os
import sys
import json
import asyncio

from dotenv import load_dotenv
load_dotenv()

from model.llm import create_model
from graph import build_multi_agent_graph
from utils.config_handler import load_project_config


def _make_config(model, thread_id: str = "email-1") -> dict:
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


async def run_test_mode(model):
    """单封测试 + CLI 交互审批"""
    from langgraph.checkpoint.memory import InMemorySaver
    from loop.hitl_handler import process_email_with_hitl, ReviewMode

    compiled = build_multi_agent_graph(model).compile(
        checkpointer=InMemorySaver()
    )
    config = _make_config(model, "test-single")

    initial_state = {
        "email_id": "test-1",
        "sender_email": "test@example.com",
        "email_subject": "退款咨询",
        "email_content": "你好，我上周购买了你们的产品，现在想申请退款，请问退款流程是怎样的？",
        "remaining_steps": 30,
    }

    print("=" * 60)
    print("Multi-Agent Email Agent — Test Mode (CLI)")
    print("=" * 60)

    result = await process_email_with_hitl(
        compiled, config, initial_state, mode=ReviewMode.CLI,
    )
    if result:
        print("\n" + "=" * 60)
        print("Final Result")
        print("=" * 60)
        print(json.dumps(_summarize(result), ensure_ascii=False, indent=2))


async def run_web_mode():
    """FastAPI Web 界面"""
    from server.app import create_app
    app = create_app()
    import uvicorn
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def run_tui_mode():
    """Textual 终端界面 + 后台 IMAP 轮询"""
    import asyncio, os
    from dotenv import load_dotenv
    load_dotenv()

    from persistence.connection import init_db, get_pool
    from rag.chroma_client import ensure_kb_initialized
    from langgraph.checkpoint.mysql.aio import AIOMySQLSaver

    await init_db()
    ensure_kb_initialized()

    project_config = load_project_config()
    model = create_model(project_config)
    pool = await get_pool()
    checkpointer = AIOMySQLSaver(conn=pool)
    compiled = build_multi_agent_graph(model).compile(checkpointer=checkpointer)

    email_queue: asyncio.Queue = asyncio.Queue()

    imap_cfg = {
        "imap_server": os.getenv("IMAP_SERVER", "imap.163.com"),
        "smtp_server": os.getenv("SMTP_SERVER", "smtp.163.com"),
        "email_address": os.getenv("EMAIL_ADDRESS", ""),
        "auth_code": os.getenv("EMAIL_AUTH_CODE", ""),
    }

    # 启动后台邮件处理链路
    from loop.engine import run_imap_poller, run_consumer
    poller_task = asyncio.create_task(run_imap_poller(email_queue, interval=60))
    consumer_task = asyncio.create_task(run_consumer(compiled, model, imap_cfg, email_queue))

    from tui.app import EmailAgentTUI
    app = EmailAgentTUI()

    try:
        await app.run_async()
    finally:
        poller_task.cancel()
        consumer_task.cancel()
        await asyncio.gather(poller_task, consumer_task, return_exceptions=True)
        from persistence.connection import close_pool
        await close_pool()


async def run_daemon_mode(model):
    """后台 agent-loop，无 UI"""
    from langgraph.checkpoint.memory import InMemorySaver
    from loop.agent_loop import EmailAgentLoop
    from rag.chroma_client import ensure_kb_initialized

    ensure_kb_initialized()
    compiled = build_multi_agent_graph(model).compile(
        checkpointer=InMemorySaver()
    )
    poll_interval = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))
    agent_loop = EmailAgentLoop(compiled, _make_config, poll_interval)

    try:
        await agent_loop.start()
    except KeyboardInterrupt:
        print("\nShutting down...")
        await agent_loop.shutdown()


def _summarize(state: dict) -> dict:
    classification = state.get("classification") or {}
    return {
        "email_id": state.get("email_id"),
        "sender_email": state.get("sender_email"),
        "subject": state.get("email_subject"),
        "intent": classification.get("intent"),
        "urgency": classification.get("urgency"),
        "topic": classification.get("topic"),
        "confidence": classification.get("confidence"),
        "draft_response": (state.get("draft_response") or "")[:200],
        "review_status": state.get("review_status"),
        "send_status": state.get("send_status"),
    }


def main():
    if "--web" in sys.argv:
        asyncio.run(run_web_mode())
    elif "--tui" in sys.argv:
        asyncio.run(run_tui_mode())
    elif "--test" in sys.argv:
        project_config = load_project_config()
        model = create_model(project_config)
        asyncio.run(run_test_mode(model))
    else:
        project_config = load_project_config()
        model = create_model(project_config)
        asyncio.run(run_daemon_mode(model))


if __name__ == "__main__":
    main()
