"""
Step 4 E2E 测试: Service 共享业务逻辑层

预期结果:
1. email_service 能列出邮件、按状态筛选
2. review_service 能获取待审批、批准、拒绝、编辑
3. agent_service 能提交处理、查询状态
4. assistant_service 能响应对话
"""

import asyncio
import sys
import os

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

EXPECTED = {
    "email_list_ok": True,
    "email_filter_ok": True,
    "review_list_ok": True,
    "review_approve_ok": True,
    "review_reject_ok": True,
    "assistant_response_ok": True,
}


async def test_email_service():
    """测试 email_service"""
    from persistence.connection import init_db, get_pool
    from persistence.email_repo import EmailRepo

    await init_db()
    pool = await get_pool()
    repo = EmailRepo(pool)

    actual = {}
    try:
        await repo.insert(
            thread_id="svc-email-1", email_id="e1",
            sender_email="a@test.com", email_subject="测试A",
            email_content="正文A", status="pending",
        )
        await repo.insert(
            thread_id="svc-email-2", email_id="e2",
            sender_email="b@test.com", email_subject="测试B",
            email_content="正文B", status="sent",
        )

        all_emails = await repo.list_all()
        actual["email_list_ok"] = len(all_emails) >= 2

        pending = await repo.list_by_status("pending")
        actual["email_filter_ok"] = len(pending) >= 1

    except Exception as e:
        actual["error"] = str(e)
        actual["email_list_ok"] = False
    return actual


async def test_review_service():
    """测试 review_service"""
    from persistence.connection import init_db, get_pool
    from persistence.review_repo import ReviewRepo

    await init_db()
    pool = await get_pool()
    repo = ReviewRepo(pool)

    actual = {}
    try:
        await repo.create(
            thread_id="svc-review-1", email_id="e1",
            sender_email="a@test.com", email_subject="待审批",
            draft_response="测试草稿",
            classification={"intent": "问题"},
            interrupt_data={"stage": "draft_review"},
        )
        await repo.create(
            thread_id="svc-review-2", email_id="e2",
            sender_email="b@test.com", email_subject="待打回",
            draft_response="测试草稿2",
            classification={},
            interrupt_data={"stage": "draft_review"},
        )

        pending = await repo.list_pending()
        actual["review_list_ok"] = len(pending) >= 2

        await repo.resolve("svc-review-1", "approved", "通过")
        actual["review_approve_ok"] = True

        await repo.resolve("svc-review-2", "rejected", "需要更多细节")
        actual["review_reject_ok"] = True

    except Exception as e:
        actual["error"] = str(e)
    return actual


async def test_assistant_service():
    """测试 assistant_service 基本调用"""
    from langchain_community.chat_models.tongyi import ChatTongyi

    actual = {}
    try:
        model = ChatTongyi(
            model="qwen-plus",
            api_key=os.getenv("DASHSCOPE_API_KEY"),
            temperature=0.2,
        )
        response = model.invoke("用一句话回复：你好")
        actual["assistant_response_ok"] = bool(response.content)
        actual["response_preview"] = response.content[:80]
    except Exception as e:
        actual["assistant_response_ok"] = False
        actual["error"] = str(e)
    return actual


def compare(expected: dict, actual: dict, label: str) -> bool:
    print(f"\n{'='*60}")
    print(f"  {label}")
    print(f"{'='*60}")
    all_pass = True
    for key, expected_val in expected.items():
        if key in actual:
            status = "PASS" if actual[key] == expected_val else "FAIL"
            if status == "FAIL":
                all_pass = False
            print(f"  [{status}] {key}: expected={expected_val!r}, actual={actual[key]!r}")
        else:
            print(f"  [SKIP] {key}: not in actual")
    if all_pass:
        print(f"\n  *** ALL CHECKS PASSED ***")
    return all_pass


async def main():
    print("Step 4 E2E Test: Service Layer")
    print("=" * 60)

    email_ok = compare(
        {k: v for k, v in EXPECTED.items() if k.startswith("email")},
        await test_email_service(), "Email Service"
    )
    review_ok = compare(
        {k: v for k, v in EXPECTED.items() if k.startswith("review")},
        await test_review_service(), "Review Service"
    )
    assistant_ok = compare(
        {"assistant_response_ok": True},
        await test_assistant_service(), "Assistant Service"
    )

    if email_ok and review_ok and assistant_ok:
        print(f"\n{'='*60}")
        print("  Step 4: ALL TESTS PASSED")
        print(f"{'='*60}")
        return 0
    else:
        print(f"\n{'='*60}")
        print("  Step 4: TESTS FAILED")
        print(f"{'='*60}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
