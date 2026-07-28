import logging

from persistence.review_repo import ReviewRepo
from persistence.email_repo import EmailRepo
from persistence.connection import get_pool

logger = logging.getLogger(__name__)


class ReviewService:
    def __init__(self):
        self._review_repo: ReviewRepo | None = None
        self._email_repo: EmailRepo | None = None

    async def _get_review_repo(self) -> ReviewRepo:
        if self._review_repo is None:
            pool = await get_pool()
            self._review_repo = ReviewRepo(pool)
        return self._review_repo

    async def _get_email_repo(self) -> EmailRepo:
        if self._email_repo is None:
            pool = await get_pool()
            self._email_repo = EmailRepo(pool)
        return self._email_repo

    async def list_pending(self) -> list[dict]:
        repo = await self._get_review_repo()
        return await repo.list_pending()

    async def approve(self, thread_id: str) -> None:
        review_repo = await self._get_review_repo()
        email_repo = await self._get_email_repo()
        await review_repo.resolve(thread_id, "approved", "已通过")
        await email_repo.update_status(thread_id, "approved")

    async def reject(self, thread_id: str, reason: str) -> None:
        review_repo = await self._get_review_repo()
        email_repo = await self._get_email_repo()
        await review_repo.resolve(thread_id, "rejected", reason)
        await email_repo.update_status(thread_id, "needs_revision")

    async def edit_and_approve(self, thread_id: str, edited_draft: str) -> None:
        review_repo = await self._get_review_repo()
        email_repo = await self._get_email_repo()
        await review_repo.resolve(thread_id, "approved", edited_draft)
        await email_repo.update_status(thread_id, "approved")
