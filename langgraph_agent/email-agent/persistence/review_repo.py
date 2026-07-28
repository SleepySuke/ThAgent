import asyncio
import json
import logging

import aiomysql

logger = logging.getLogger(__name__)

_pending_events: dict[str, asyncio.Event] = {}


class ReviewRepo:
    def __init__(self, pool: aiomysql.Pool):
        self.pool = pool

    async def create(
        self,
        thread_id: str,
        email_id: str = "",
        sender_email: str = "",
        email_subject: str = "",
        draft_response: str = "",
        classification: dict | None = None,
        interrupt_data: dict | None = None,
    ) -> None:
        sql = """INSERT INTO review_queue
            (thread_id, email_id, sender_email, email_subject,
             draft_response, classification_json, interrupt_data, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending')
        AS new_row ON DUPLICATE KEY UPDATE
            draft_response=new_row.draft_response, status='pending',
            interrupt_data=new_row.interrupt_data,
            created_at=CURRENT_TIMESTAMP, resolved_at=NULL"""
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, (
                    thread_id, email_id, sender_email, email_subject,
                    draft_response,
                    json.dumps(classification, ensure_ascii=False) if classification else None,
                    json.dumps(interrupt_data, ensure_ascii=False) if interrupt_data else None,
                ))

    async def list_pending(self) -> list[dict]:
        sql = "SELECT * FROM review_queue WHERE status = 'pending' ORDER BY created_at ASC"
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql)
                rows = await cur.fetchall()
        return rows or []

    async def get_by_thread_id(self, thread_id: str) -> dict | None:
        sql = "SELECT * FROM review_queue WHERE thread_id = %s"
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, (thread_id,))
                row = await cur.fetchone()
        return row

    async def resolve(self, thread_id: str, status: str, comment: str = "") -> None:
        sql = """UPDATE review_queue SET status = %s, review_comment = %s,
                 resolved_at = NOW() WHERE thread_id = %s"""
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, (status, comment, thread_id))

        event = _pending_events.pop(thread_id, None)
        if event:
            event.set()

    async def wait_for_resolution(self, thread_id: str, timeout: float = 300) -> dict:
        event = asyncio.Event()
        _pending_events[thread_id] = event

        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            _pending_events.pop(thread_id, None)
            return {"status": "timeout", "error": "审批超时"}

        row = await self.get_by_thread_id(thread_id)
        if row is None:
            return {"status": "unknown", "error": "记录不存在"}
        return {
            "status": row.get("status", "unknown"),
            "comment": row.get("review_comment", ""),
        }
