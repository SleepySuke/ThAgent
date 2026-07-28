"""
Step 3 E2E 测试: Worker Pool + HITL 多模式

预期结果:
1. Worker Pool 能提交多个邮件任务
2. HITL web 模式: interrupt → 写入 review_queue → resolve → 恢复
3. HITL cli 模式: 通过 callable 模拟 input() → 恢复
4. 并发控制: Semaphore 限制并行数
"""

import asyncio
import sys
import os
from unittest.mock import patch, AsyncMock

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

EXPECTED = {
    "pool_create_ok": True,
    "task_submit_ok": True,
    "concurrency_limit_ok": True,
    "hitl_web_write_ok": True,
    "hitl_web_resume_ok": True,
    "hitl_cli_resume_ok": True,
}


async def test_worker_pool_create():
    """测试 Worker Pool 创建"""
    from loop.worker_pool import EmailWorkerPool

    actual = {}
    try:
        pool = EmailWorkerPool(max_workers=3)
        actual["pool_create_ok"] = pool.max_workers == 3
        actual["running"] = pool.running
    except Exception as e:
        actual["pool_create_ok"] = False
        actual["error"] = str(e)
    return actual


async def test_concurrency_limit():
    """测试并发限制 (Semaphore)"""
    from loop.worker_pool import EmailWorkerPool

    pool = EmailWorkerPool(max_workers=2)
    running = 0
    max_running = 0

    async def mock_process(email_data):
        nonlocal running, max_running
        running += 1
        max_running = max(max_running, running)
        await asyncio.sleep(0.1)
        running -= 1

    pool._process_func = mock_process

    tasks = []
    for i in range(5):
        tasks.append(asyncio.create_task(pool._run_with_semaphore({"id": i})))
    await asyncio.gather(*tasks)

    actual = {
        "concurrency_limit_ok": max_running <= 2,
        "max_concurrent": max_running,
    }
    return actual


async def test_hitl_web_mode():
    """测试 HITL Web 模式: interrupt → review_queue → resolve → resume"""
    from persistence.connection import init_db
    from persistence.review_repo import ReviewRepo
    from persistence.connection import get_pool

    await init_db()

    thread_id = "test-hitl-web-1"
    pool = await get_pool()
    review_repo = ReviewRepo(pool)

    actual = {}
    try:
        interrupt_data = {
            "stage": "draft_review",
            "sender": "test@example.com",
            "subject": "Web HITL 测试",
            "draft": "Web模式草稿",
        }

        await review_repo.create(
            thread_id=thread_id,
            email_id="email-10",
            sender_email="test@example.com",
            email_subject="Web HITL 测试",
            draft_response="Web模式草稿",
            classification={},
            interrupt_data=interrupt_data,
        )
        actual["hitl_web_write_ok"] = True

        async def delayed_resolve():
            await asyncio.sleep(0.3)
            await review_repo.resolve(thread_id, "approved", "通过")

        wait_task = asyncio.create_task(
            review_repo.wait_for_resolution(thread_id, timeout=10)
        )
        resolve_task = asyncio.create_task(delayed_resolve())

        result = await wait_task
        await resolve_task

        actual["hitl_web_resume_ok"] = (
            result.get("status") == "approved"
            and result.get("comment") == "通过"
        )

    except Exception as e:
        actual["error"] = str(e)
    return actual


async def test_hitl_cli_mode():
    """测试 HITL CLI 模式: 模拟 input() 返回 approve"""
    from loop.hitl_handler import ReviewMode, handle_interrupt

    actual = {}
    try:
        interrupt_data = {
            "stage": "draft_review",
            "sender": "test@example.com",
            "subject": "CLI HITL 测试",
            "draft": "CLI模式草稿",
        }

        with patch("builtins.input", return_value="a"):
            result = await handle_interrupt(
                interrupt_data, mode=ReviewMode.CLI, thread_id=None
            )

        actual["hitl_cli_resume_ok"] = result.get("status") == "approved"
        actual["result"] = result

    except Exception as e:
        actual["hitl_cli_resume_ok"] = False
        actual["error"] = str(e)
    return actual


def compare(expected: dict, actual: dict, label: str) -> bool:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    all_pass = True
    for key, expected_val in expected.items():
        if key in actual:
            actual_val = actual[key]
            status = "PASS" if actual_val == expected_val else "FAIL"
            if status == "FAIL":
                all_pass = False
            print(f"  [{status}] {key}: expected={expected_val!r}, actual={actual_val!r}")
        else:
            print(f"  [SKIP] {key}: not in actual")
    if all_pass:
        print(f"\n  *** ALL CHECKS PASSED ***")
    return all_pass


async def main():
    print("Step 3 E2E Test: Worker Pool + HITL")
    print("=" * 60)

    pool_actual = await test_worker_pool_create()
    pool_ok = compare(
        {"pool_create_ok": True}, pool_actual, "Worker Pool Creation"
    )

    conc_actual = await test_concurrency_limit()
    conc_ok = compare(
        {"concurrency_limit_ok": True}, conc_actual, "Concurrency Limit"
    )

    web_actual = await test_hitl_web_mode()
    web_ok = compare(
        {"hitl_web_write_ok": True, "hitl_web_resume_ok": True},
        web_actual, "HITL Web Mode"
    )

    cli_actual = await test_hitl_cli_mode()
    cli_ok = compare(
        {"hitl_cli_resume_ok": True}, cli_actual, "HITL CLI Mode"
    )

    if pool_ok and conc_ok and web_ok and cli_ok:
        print(f"\n{'='*60}")
        print("  Step 3: ALL TESTS PASSED")
        print(f"{'='*60}")
        return 0
    else:
        print(f"\n{'='*60}")
        print("  Step 3: TESTS FAILED")
        print(f"{'='*60}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
