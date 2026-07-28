import json
import logging

import aiomysql

logger = logging.getLogger(__name__)


class EmailRepo:
    def __init__(self, pool: aiomysql.Pool):
        self.pool = pool

    async def insert(
        self,
        thread_id: str,
        email_id: str = "",
        sender_email: str = "",
        email_subject: str = "",
        email_content: str = "",
        classification: dict | None = None,
        search_results: list | None = None,
        status: str = "pending",
    ) -> None:
        sql = """INSERT INTO email_history
            (thread_id, email_id, sender_email, email_subject, email_content,
             classification_json, search_results_json, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        AS new_row ON DUPLICATE KEY UPDATE
            email_subject=new_row.email_subject, status=new_row.status,
            classification_json=new_row.classification_json,
            search_results_json=new_row.search_results_json"""
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, (
                    thread_id, email_id, sender_email, email_subject,
                    email_content,
                    json.dumps(classification, ensure_ascii=False) if classification else None,
                    json.dumps(search_results, ensure_ascii=False) if search_results else None,
                    status,
                ))

    async def get_by_thread_id(self, thread_id: str) -> dict | None:
        sql = "SELECT * FROM email_history WHERE thread_id = %s"
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, (thread_id,))
                row = await cur.fetchone()
        return row

    async def list_by_status(self, status: str, limit: int = 50) -> list[dict]:
        sql = """SELECT * FROM email_history
                 WHERE status = %s ORDER BY created_at DESC LIMIT %s"""
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, (status, limit))
                rows = await cur.fetchall()
        return rows or []

    async def list_all(self, status: str | None = None, limit: int = 50, offset: int = 0) -> list[dict]:
        if status:
            sql = """SELECT * FROM email_history
                     WHERE status = %s ORDER BY created_at DESC LIMIT %s OFFSET %s"""
            params = (status, limit, offset)
        else:
            sql = """SELECT * FROM email_history
                     ORDER BY created_at DESC LIMIT %s OFFSET %s"""
            params = (limit, offset)
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql, params)
                rows = await cur.fetchall()
        return rows or []

    async def update_status(self, thread_id: str, status: str) -> None:
        sql = "UPDATE email_history SET status = %s WHERE thread_id = %s"
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, (status, thread_id))

    async def update_after_processing(
        self, thread_id: str, classification: dict | None = None,
        search_results: list | None = None, draft_response: str = "",
        review_status: str = "", send_status: str = "",
        status: str = "",
    ) -> None:
        sql = """UPDATE email_history SET
            classification_json = COALESCE(%s, classification_json),
            search_results_json = COALESCE(%s, search_results_json),
            draft_response = %s, review_status = %s,
            send_status = %s, status = %s
        WHERE thread_id = %s"""
        async with self.pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(sql, (
                    json.dumps(classification, ensure_ascii=False) if classification else None,
                    json.dumps(search_results, ensure_ascii=False) if search_results else None,
                    draft_response, review_status, send_status, status, thread_id,
                ))

    async def count_by_status(self) -> dict[str, int]:
        sql = """SELECT status, COUNT(*) as cnt FROM email_history GROUP BY status"""
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(sql)
                rows = await cur.fetchall()
        return {r["status"]: r["cnt"] for r in (rows or [])}
