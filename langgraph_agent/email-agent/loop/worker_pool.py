import asyncio
import logging
import time

logger = logging.getLogger(__name__)


class EmailWorkerPool:
    """异步 Worker Pool — 并发处理多封邮件，Semaphore 限流"""

    def __init__(self, max_workers: int = 3):
        self.max_workers = max_workers
        self.semaphore = asyncio.Semaphore(max_workers)
        self.active_tasks: dict[str, asyncio.Task] = {}
        self.running = False
        self._process_func = None

    def set_process_func(self, func):
        """设置邮件处理函数: async func(email_data) -> None"""
        self._process_func = func

    async def submit(self, email_data: dict) -> str:
        """提交一封邮件到 pool，返回 thread_id"""
        thread_id = f"email-{email_data.get('email_id', 'unknown')}-{int(time.time())}"
        task = asyncio.create_task(
            self._run_with_semaphore(email_data, thread_id),
            name=f"email-{thread_id}",
        )
        self.active_tasks[thread_id] = task
        return thread_id

    async def _run_with_semaphore(self, email_data: dict, thread_id: str = ""):
        async with self.semaphore:
            try:
                if self._process_func:
                    await self._process_func(email_data, thread_id)
            except Exception:
                logger.exception("Worker failed for %s", thread_id)
            finally:
                self.active_tasks.pop(thread_id, None)

    async def start(self, email_queue: asyncio.Queue):
        """启动消费者循环，从 queue 取邮件提交到 pool"""
        self.running = True
        logger.info("Worker pool started (max_workers=%d)", self.max_workers)

        while self.running:
            try:
                email_data = await asyncio.wait_for(
                    email_queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue

            await self.submit(email_data)
            email_queue.task_done()

        logger.info("Worker pool stopped")

    async def shutdown(self):
        self.running = False
        tasks = list(self.active_tasks.values())
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        logger.info("Worker pool shut down")
