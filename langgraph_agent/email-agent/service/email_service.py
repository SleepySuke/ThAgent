import logging

from persistence.email_repo import EmailRepo
from persistence.connection import get_pool

logger = logging.getLogger(__name__)


class EmailService:
    def __init__(self):
        self._repo: EmailRepo | None = None

    async def _get_repo(self) -> EmailRepo:
        if self._repo is None:
            pool = await get_pool()
            self._repo = EmailRepo(pool)
        return self._repo

    async def list_emails(self, status: str | None = None,
                          limit: int = 50, offset: int = 0) -> list[dict]:
        repo = await self._get_repo()
        return await repo.list_all(status=status, limit=limit, offset=offset)

    async def get_email(self, thread_id: str) -> dict | None:
        repo = await self._get_repo()
        return await repo.get_by_thread_id(thread_id)

    async def update_status(self, thread_id: str, status: str) -> None:
        repo = await self._get_repo()
        await repo.update_status(thread_id, status)

    async def get_stats(self) -> dict:
        repo = await self._get_repo()
        counts = await repo.count_by_status()
        return {
            "pending": counts.get("pending", 0),
            "processing": counts.get("processing", 0),
            "awaiting_review": counts.get("awaiting_review", 0),
            "sent": counts.get("sent", 0),
            "failed": counts.get("failed", 0),
            "total": sum(counts.values()),
        }
