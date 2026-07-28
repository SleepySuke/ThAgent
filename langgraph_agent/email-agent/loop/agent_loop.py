import asyncio
import logging
import signal
import time

logger = logging.getLogger(__name__)


class EmailAgentLoop:
    """异步 Agent-Loop：后台轮询邮件 + 单消费者处理 + CLI HITL。"""

    def __init__(self, graph, make_config, poll_interval: int = 60):
        self.graph = graph
        self.make_config = make_config
        self.poll_interval = poll_interval
        self.email_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._tasks: list[asyncio.Task] = []

    async def start(self):
        """启动 agent-loop"""
        self._running = True
        logger.info("Agent loop starting (poll interval: %ds)", self.poll_interval)

        dummy_config = self.make_config("poller")
        imap_cfg = dummy_config.get("configurable", {})

        poller = asyncio.create_task(
            _poller_loop(
                self.email_queue, imap_cfg, self.poll_interval, lambda: self._running
            ),
            name="imap-poller",
        )
        consumer = asyncio.create_task(
            self._consume_emails(), name="email-consumer"
        )
        self._tasks = [poller, consumer]

        logger.info("Agent loop started. Press Ctrl+C to stop.")

        try:
            done, pending = await asyncio.wait(
                self._tasks,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                if task.exception():
                    logger.error("Task failed: %s", task.exception())
        except asyncio.CancelledError:
            pass

    async def _consume_emails(self):
        """单消费者：从队列取出邮件并逐一处理"""
        while self._running:
            try:
                email_data = await asyncio.wait_for(
                    self.email_queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue

            thread_id = f"email-{email_data.get('email_id', 'unknown')}-{int(time.time())}"
            config = self.make_config(thread_id)

            initial_state = {
                "email_id": email_data.get("email_id"),
                "sender_email": email_data.get("sender_email"),
                "email_subject": email_data.get("email_subject"),
                "email_content": email_data.get("email_content"),
                "remaining_steps": 30,
            }

            from loop.hitl_handler import process_email_with_hitl

            try:
                logger.info("Processing email: %s", thread_id)
                result = await process_email_with_hitl(
                    self.graph, config, initial_state
                )
                if result:
                    status = result.get("send_status", "unknown")
                    logger.info("Email %s processed: %s", thread_id, status)
            except Exception:
                logger.exception("Failed processing email %s", thread_id)
            finally:
                self.email_queue.task_done()

    async def shutdown(self):
        """优雅关闭 agent-loop"""
        logger.info("Shutting down agent loop...")
        self._running = False
        for task in self._tasks:
            if not task.done():
                task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        logger.info("Agent loop stopped.")


async def _poller_loop(queue, imap_cfg, interval, is_running):
    """IMAP 轮询包装器"""
    from loop.imap_poller import imap_poller_task
    await imap_poller_task(queue, imap_cfg, interval)
