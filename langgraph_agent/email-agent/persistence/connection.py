import os
import logging

import aiomysql
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

_pool: aiomysql.Pool | None = None

DDL_EMAIL_HISTORY = """
CREATE TABLE IF NOT EXISTS email_history (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    thread_id VARCHAR(128) NOT NULL UNIQUE,
    email_id VARCHAR(255) DEFAULT '',
    sender_email VARCHAR(255) DEFAULT '',
    email_subject VARCHAR(500) DEFAULT '',
    email_content TEXT,
    classification_json JSON,
    search_results_json JSON,
    draft_response TEXT,
    review_status VARCHAR(32) DEFAULT '',
    send_status VARCHAR(32) DEFAULT '',
    status VARCHAR(32) DEFAULT 'pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_status (status),
    INDEX idx_thread_id (thread_id),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""

DDL_REVIEW_QUEUE = """
CREATE TABLE IF NOT EXISTS review_queue (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    thread_id VARCHAR(128) NOT NULL UNIQUE,
    email_id VARCHAR(255) DEFAULT '',
    sender_email VARCHAR(255) DEFAULT '',
    email_subject VARCHAR(500) DEFAULT '',
    draft_response TEXT,
    classification_json JSON,
    interrupt_data JSON,
    status VARCHAR(32) DEFAULT 'pending',
    review_comment TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    resolved_at DATETIME NULL,
    INDEX idx_status (status),
    INDEX idx_thread_id (thread_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
"""


async def get_pool() -> aiomysql.Pool:
    global _pool
    if _pool is None:
        _pool = await aiomysql.create_pool(
            host=os.getenv("MYSQL_HOST", "127.0.0.1"),
            port=int(os.getenv("MYSQL_PORT", "3306")),
            user=os.getenv("MYSQL_USER", "root"),
            password=os.getenv("MYSQL_PASSWORD", ""),
            db=os.getenv("MYSQL_DATABASE", "email_agent"),
            minsize=2,
            maxsize=10,
            autocommit=True,
        )
        logger.info("MySQL pool created: %s:%s/%s",
                     os.getenv("MYSQL_HOST"), os.getenv("MYSQL_PORT"), os.getenv("MYSQL_DATABASE"))
    return _pool


async def init_db() -> None:
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute(DDL_EMAIL_HISTORY)
            await cur.execute(DDL_REVIEW_QUEUE)
    logger.info("Database tables initialized")


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        await _pool.wait_closed()
        _pool = None
        logger.info("MySQL pool closed")
