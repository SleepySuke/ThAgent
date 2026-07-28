import asyncio
import logging

logger = logging.getLogger(__name__)


async def imap_poller_task(queue: asyncio.Queue, config: dict, interval: int = 60):
    """IMAP 轮询协程：定时检查未读邮件并加入队列。

    Args:
        queue: 邮件队列 (asyncio.Queue)
        config: 包含 IMAP 连接信息的配置
        interval: 轮询间隔秒数 (默认 60)
    """
    imap_server = config.get("imap_server", "imap.163.com")
    email_address = config.get("email_address", "")
    auth_code = config.get("auth_code", "")

    if not email_address or not auth_code:
        logger.warning("IMAP credentials not configured, poller will not fetch emails")
        await asyncio.sleep(interval * 1000)
        return

    loop = asyncio.get_event_loop()

    while True:
        try:
            emails = await loop.run_in_executor(
                None,
                _fetch_emails_sync,
                imap_server,
                email_address,
                auth_code,
            )

            for email_data in emails or []:
                await queue.put(email_data)
                logger.info(
                    "New email: %s from %s",
                    email_data.get("email_subject"),
                    email_data.get("sender_email"),
                )

        except asyncio.CancelledError:
            logger.info("IMAP poller cancelled")
            return
        except Exception:
            logger.exception("IMAP poll error")

        await asyncio.sleep(interval)


def _fetch_emails_sync(imap_server: str, email_address: str, auth_code: str) -> list[dict]:
    """同步获取未读邮件，在 run_in_executor(线程池) 中运行。"""
    from utils.email_client import fetch_emails
    return list(fetch_emails(
        imap_server=imap_server,
        email_address=email_address,
        auth_code=auth_code,
    ))
