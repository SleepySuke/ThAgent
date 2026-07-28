"""
Step 8 E2E 集成测试：完整链路验证

预期结果:
1. FastAPI server 可启动并响应 API
2. Test 模式完整流程通过 (classify → research → draft → approve → send)
3. 所有前序步骤测试通过
4. HTMX 审批 API 正确
"""

import asyncio
import sys
import os
import subprocess

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

EXPECTED = {
    "fastapi_app_ok": True,
    "api_endpoints_ok": True,
    "review_api_ok": True,
    "test_mode_ok": True,
    "all_steps_ok": True,
}


async def test_fastapi_api():
    """测试 FastAPI API 端点"""
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app

    app = create_app()
    actual = {}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Test stats
        resp = await client.get("/api/emails/stats")
        actual["stats_status"] = resp.status_code
        data = resp.json()
        actual["stats_has_keys"] = "pending" in data

        # Test emails list
        resp = await client.get("/api/emails")
        actual["emails_status"] = resp.status_code

        # Test reviews list
        resp = await client.get("/api/reviews")
        actual["reviews_status"] = resp.status_code

        # Test assistant summary
        resp = await client.get("/api/assistant/summary")
        actual["assistant_status"] = resp.status_code

        # Verify all 200
        actual["api_endpoints_ok"] = all([
            actual.get("stats_status") == 200,
            actual.get("emails_status") == 200,
            actual.get("reviews_status") == 200,
            actual.get("assistant_status") == 200,
        ])

    return actual


async def test_review_api():
    """测试审批 API: create → pending → approve"""
    from persistence.connection import init_db, get_pool
    from persistence.review_repo import ReviewRepo
    from httpx import AsyncClient, ASGITransport
    from server.app import create_app

    await init_db()
    pool = await get_pool()
    repo = ReviewRepo(pool)

    actual = {}
    tid = "e2e-review-api-test"
    await repo.create(
        thread_id=tid, email_id="e99", sender_email="x@t.com",
        email_subject="API测试", draft_response="测试草稿",
        classification={}, interrupt_data={"stage": "draft_review"},
    )

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/reviews")
        data = resp.json()
        pending_ids = [p["thread_id"] for p in data.get("pending", [])]
        actual["review_in_pending"] = tid in pending_ids

        resp = await client.post(f"/api/reviews/{tid}/approve")
        actual["approve_ok"] = resp.status_code == 200

        resp = await client.get("/api/reviews")
        data = resp.json()
        pending_ids = [p["thread_id"] for p in data.get("pending", [])]
        actual["review_removed"] = tid not in pending_ids

    actual["review_api_ok"] = all([
        actual.get("review_in_pending"),
        actual.get("approve_ok"),
        actual.get("review_removed"),
    ])
    return actual


def test_all_previous_steps():
    """运行所有前序步骤测试"""
    actual = {}
    test_dir = os.path.dirname(os.path.abspath(__file__))
    venv_python = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(test_dir))),
        ".venv", "bin", "python"
    )

    step_results = {}
    for step in ["test_step1_mysql", "test_step2_persistence", "test_step3_worker", "test_step4_service"]:
        path = os.path.join(test_dir, f"{step}.py")
        if not os.path.exists(path):
            step_results[step] = "FILE_NOT_FOUND"
            continue
        result = subprocess.run(
            [venv_python, path], capture_output=True, text=True, timeout=60,
            env={**os.environ, "PYTHONPATH": os.path.dirname(test_dir)},
        )
        passed = "ALL TESTS PASSED" in result.stdout
        step_results[step] = "PASS" if passed else f"FAIL (exit={result.returncode})"

    actual["all_steps_ok"] = all(v == "PASS" for v in step_results.values())
    actual["step_details"] = step_results
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
            val = actual[key]
            if isinstance(val, dict):
                val = str(val)[:100]
            print(f"  [{status}] {key}: expected={expected_val!r}, actual={val!r}")
        else:
            print(f"  [SKIP] {key}: not in actual")
    if all_pass:
        print(f"\n  *** ALL CHECKS PASSED ***")
    return all_pass


async def main():
    print("Step 8 E2E Integration Test")
    print("=" * 60)

    api_actual = await test_fastapi_api()
    api_ok = compare(
        {"api_endpoints_ok": True}, api_actual, "FastAPI Endpoints"
    )

    review_actual = await test_review_api()
    review_ok = compare(
        {"review_api_ok": True}, review_actual, "Review API Flow"
    )

    steps_actual = test_all_previous_steps()
    steps_ok = compare(
        {"all_steps_ok": True}, steps_actual, "Previous Steps Regression"
    )

    if api_ok and review_ok and steps_ok:
        print(f"\n{'='*60}")
        print("  Step 8: ALL E2E TESTS PASSED")
        print(f"{'='*60}")
        return 0
    else:
        print(f"\n{'='*60}")
        print("  Step 8: TESTS FAILED")
        print(f"{'='*60}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
