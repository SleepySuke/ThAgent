"""
Step 2 E2E 测试：MySQL 持久化层

预期结果：
1. 连接池单例创建成功
2. email_history 表和 review_queue 表存在
3. email_repo 增删改查正确
4. review_repo 创建+审批决议+等待机制正确
"""

import asyncio
import sys
import os

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

EXPECTED = {
    "tables_exist": ["email_history", "review_queue"],
    "insert_ok": True,
    "query_by_thread_id_ok": True,
    "query_by_status_ok": True,
    "update_status_ok": True,
    "review_create_ok": True,
    "review_resolve_ok": True,
    "review_wait_ok": True,
}


async def _get_pool():
    import aiomysql
    return await aiomysql.create_pool(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        db=os.getenv("MYSQL_DATABASE", "email_agent"),
        minsize=1, maxsize=5, autocommit=True,
    )


async def test_tables_exist():
    """测试表结构存在"""
    pool = await _get_pool()
    actual = {}
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SHOW TABLES")
                tables = [t[0] for t in await cur.fetchall()]
                actual["tables_exist"] = tables
    finally:
        pool.close()
        await pool.wait_closed()
    return actual


async def test_email_repo():
    """测试 email_repo 增删改查"""
    from persistence.email_repo import EmailRepo

    pool = await _get_pool()
    actual = {}
    try:
        repo = EmailRepo(pool)

        # 1. Insert
        await repo.insert(
            thread_id="test-thread-1",
            email_id="email-001",
            sender_email="test@example.com",
            email_subject="测试主题",
            email_content="测试正文内容",
            classification={
                "intent": "问题", "urgency": "low",
                "confidence": 0.9, "topic": "测试", "summary": "测试摘要"
            },
        )
        actual["insert_ok"] = True

        # 2. Query by thread_id
        record = await repo.get_by_thread_id("test-thread-1")
        actual["query_by_thread_id_ok"] = (
            record is not None
            and record["thread_id"] == "test-thread-1"
            and record["sender_email"] == "test@example.com"
            and record["email_subject"] == "测试主题"
        )

        # 3. Query by status
        records = await repo.list_by_status("pending")
        actual["query_by_status_ok"] = len(records) >= 1

        # 4. Update status
        await repo.update_status("test-thread-1", "sent")
        updated = await repo.get_by_thread_id("test-thread-1")
        actual["update_status_ok"] = (
            updated is not None and updated["status"] == "sent"
        )

    except Exception as e:
        actual["error"] = str(e)
        actual["insert_ok"] = False
    finally:
        pool.close()
        await pool.wait_closed()
    return actual


async def test_review_repo():
    """测试 review_repo 审批队列"""
    from persistence.review_repo import ReviewRepo

    pool = await _get_pool()
    actual = {}
    try:
        repo = ReviewRepo(pool)

        # 1. Create review
        interrupt_data = {
            "stage": "draft_review",
            "sender": "test@example.com",
            "subject": "审批测试",
            "draft": "这是测试草稿内容。",
            "classification": {"intent": "问题", "urgency": "low"},
        }
        await repo.create(
            thread_id="test-review-1",
            email_id="email-002",
            sender_email="test@example.com",
            email_subject="审批测试",
            draft_response="这是测试草稿内容。",
            classification=interrupt_data["classification"],
            interrupt_data=interrupt_data,
        )
        actual["review_create_ok"] = True

        # 2. Query pending reviews
        pending = await repo.list_pending()
        actual["review_list_ok"] = len(pending) >= 1

        # 3. Resolve review (approve)
        await repo.resolve("test-review-1", "approved", comment="通过")
        actual["review_resolve_ok"] = True

        # 4. Wait mechanism (asyncio.Event)
        async def delayed_approve():
            await asyncio.sleep(0.5)
            await repo.resolve("test-review-2", "approved")

        await repo.create(
            thread_id="test-review-2",
            email_id="email-003",
            sender_email="test2@example.com",
            email_subject="等待测试",
            draft_response="等待决议的草稿",
            classification={},
            interrupt_data={"stage": "draft_review"},
        )

        wait_task = asyncio.create_task(
            repo.wait_for_resolution("test-review-2")
        )
        approve_task = asyncio.create_task(delayed_approve())

        result = await asyncio.wait_for(wait_task, timeout=5.0)
        await approve_task
        actual["review_wait_ok"] = (
            isinstance(result, dict)
            and result.get("status") == "approved"
        )

    except Exception as e:
        actual["error"] = str(e)
    finally:
        pool.close()
        await pool.wait_closed()
    return actual


def compare(expected: dict, actual: dict, label: str) -> bool:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    all_pass = True
    for key, expected_val in expected.items():
        if key in actual:
            actual_val = actual[key]
            if isinstance(expected_val, bool):
                status = "PASS" if actual_val == expected_val else "FAIL"
            elif isinstance(expected_val, list):
                status = "PASS" if set(expected_val).issubset(set(actual_val)) else "FAIL"
            else:
                status = "PASS" if actual_val == expected_val else "FAIL"
            if status == "FAIL":
                all_pass = False
            print(f"  [{status}] {key}: expected={expected_val!r}, actual={actual_val!r}")
        else:
            all_pass = False
            print(f"  [FAIL] {key}: MISSING from actual result")
    if all_pass:
        print(f"\n  *** ALL CHECKS PASSED ***")
    return all_pass


async def main():
    print("Step 2 E2E Test: MySQL Persistence Layer")
    print("=" * 60)

    # 先初始化表结构
    from persistence.connection import init_db
    await init_db()
    print("  Tables initialized.\n")

    tables_actual = await test_tables_exist()
    tables_ok = compare(
        {"tables_exist": EXPECTED["tables_exist"]},
        tables_actual, "Table Existence"
    )

    email_ok = compare(
        {k: v for k, v in EXPECTED.items() if k in ("insert_ok", "query_by_thread_id_ok", "query_by_status_ok", "update_status_ok")},
        await test_email_repo(), "EmailRepo CRUD"
    )

    review_ok = compare(
        {k: v for k, v in EXPECTED.items() if k in ("review_create_ok", "review_resolve_ok", "review_wait_ok")},
        await test_review_repo(), "ReviewRepo Queue"
    )

    if tables_ok and email_ok and review_ok:
        print(f"\n{'='*60}")
        print("  Step 2: ALL TESTS PASSED")
        print(f"{'='*60}")
        return 0
    else:
        print(f"\n{'='*60}")
        print("  Step 2: TESTS FAILED")
        print(f"{'='*60}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
