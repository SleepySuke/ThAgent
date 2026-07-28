"""邮件处理引擎 — IMAP 轮询 + 消费者，供 Web 和 TUI 模式共享"""
import asyncio
import logging
import os

from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


async def run_imap_poller(queue: asyncio.Queue, interval: int = 60):
    """后台 IMAP 轮询协程"""
    from utils.email_client import fetch_emails

    imap_server = os.getenv("IMAP_SERVER", "imap.163.com")
    email_addr = os.getenv("EMAIL_ADDRESS", "")
    auth_code = os.getenv("EMAIL_AUTH_CODE", "")

    if not email_addr or not auth_code:
        logger.warning("IMAP credentials not set, poller idle")
        while True:
            await asyncio.sleep(interval)

    loop = asyncio.get_event_loop()

    while True:
        try:
            emails = await loop.run_in_executor(
                None, lambda: list(fetch_emails(
                    imap_server=imap_server,
                    email_address=email_addr,
                    auth_code=auth_code,
                ))
            )
            for email_data in emails:
                await queue.put(email_data)
                logger.info("New email: %s from %s",
                            email_data.get("email_subject", "")[:40],
                            email_data.get("sender_email", ""))

        except asyncio.CancelledError:
            logger.info("IMAP poller cancelled")
            return
        except Exception:
            logger.exception("IMAP poll error")

        await asyncio.sleep(interval)


async def run_consumer(graph, model, imap_cfg: dict, queue: asyncio.Queue):
    """后台邮件消费者: 从队列取邮件, 通过 multi-agent graph 处理"""
    from loop.hitl_handler import process_email_with_hitl, ReviewMode
    from persistence.email_repo import EmailRepo
    from persistence.connection import get_pool

    while True:
        try:
            email_data = await asyncio.wait_for(queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            logger.info("Consumer cancelled")
            return

        thread_id = f"email-{email_data.get('email_id', 'unknown')}"
        config = {
            "configurable": {
                "thread_id": thread_id,
                "model": model,
                "imap_server": imap_cfg.get("imap_server", ""),
                "smtp_server": imap_cfg.get("smtp_server", ""),
                "email_address": imap_cfg.get("email_address", ""),
                "auth_code": imap_cfg.get("auth_code", ""),
            }
        }
        initial_state = {
            "email_id": email_data.get("email_id"),
            "sender_email": email_data.get("sender_email"),
            "email_subject": email_data.get("email_subject"),
            "email_content": email_data.get("email_content"),
            "remaining_steps": 30,
        }

        try:
            pool = await get_pool()
            repo = EmailRepo(pool)
            await repo.insert(
                thread_id=thread_id,
                email_id=email_data.get("email_id", ""),
                sender_email=email_data.get("sender_email", ""),
                email_subject=email_data.get("email_subject", ""),
                email_content=email_data.get("email_content", ""),
                status="processing",
            )
        except Exception:
            logger.exception("Failed to insert email record")

        try:
            logger.info("Processing: %s", thread_id)
            result = await process_email_with_hitl(
                graph, config, initial_state, mode=ReviewMode.WEB,
            )
            if result:
                classification = result.get("classification") or {}
                await repo.update_after_processing(
                    thread_id=thread_id,
                    classification=classification,
                    search_results=result.get("search_results"),
                    draft_response=result.get("draft_response", ""),
                    review_status=result.get("review_status", ""),
                    send_status=result.get("send_status", ""),
                    status=result.get("send_status") == "sent" and "sent" or "failed",
                )
                logger.info("Processed %s: send_status=%s", thread_id, result.get("send_status"))
        except Exception:
            logger.exception("Failed processing %s", thread_id)
            await repo.update_status(thread_id, "failed")
        finally:
            queue.task_done()
