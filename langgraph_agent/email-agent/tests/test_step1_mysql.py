"""
Step 1 E2E 测试：Docker MySQL + 依赖验证

预期结果：
1. MySQL 容器运行在 localhost:3306
2. 数据库 email_agent 存在
3. aiomysql 连接池创建成功
4. AIOMySQLSaver 创建成功
"""

import asyncio
import sys
import os

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

MYSQL_HOST = os.getenv("MYSQL_HOST", "127.0.0.1")
MYSQL_PORT = int(os.getenv("MYSQL_PORT", "3306"))
MYSQL_USER = os.getenv("MYSQL_USER", "root")
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "")
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "email_agent")

EXPECTED = {
    "host": MYSQL_HOST,
    "port": MYSQL_PORT,
    "database": MYSQL_DATABASE,
    "pool_created": True,
    "saver_created": True,
}


async def test_mysql_connection():
    """测试 MySQL 连接"""
    import aiomysql

    actual = {}
    try:
        pool = await aiomysql.create_pool(
            host=MYSQL_HOST,
            port=MYSQL_PORT,
            user=MYSQL_USER,
            password=MYSQL_PASSWORD,
            db=MYSQL_DATABASE,
            minsize=1,
            maxsize=5,
        )
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT 1")
                result = await cur.fetchone()
                actual["pool_created"] = result == (1,)

                await cur.execute("SHOW TABLES")
                tables = await cur.fetchall()
                actual["table_count"] = len(tables)
                actual["tables"] = [t[0] for t in tables]

        pool.close()
        await pool.wait_closed()
        actual["host"] = MYSQL_HOST
        actual["port"] = MYSQL_PORT
        actual["database"] = MYSQL_DATABASE

    except Exception as e:
        actual["error"] = str(e)
        actual["pool_created"] = False

    return actual


async def test_saver():
    """测试 AIOMySQLSaver 创建"""
    from langgraph.checkpoint.mysql.aio import AIOMySQLSaver
    import aiomysql

    actual = {}
    try:
        pool = await aiomysql.create_pool(
            host=MYSQL_HOST, port=MYSQL_PORT,
            user=MYSQL_USER, password=MYSQL_PASSWORD,
            db=MYSQL_DATABASE, minsize=1, maxsize=5,
        )
        saver = AIOMySQLSaver(conn=pool)
        actual["saver_created"] = True
        actual["saver_type"] = type(saver).__name__

        pool.close()
        await pool.wait_closed()
    except Exception as e:
        actual["saver_created"] = False
        actual["error"] = str(e)

    return actual


def compare(expected: dict, actual: dict, label: str) -> bool:
    """比较预期和实际结果"""
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
            print(f"  [SKIP] {key}: not in actual result")

    if all_pass:
        print(f"\n  *** ALL CHECKS PASSED ***")
    else:
        print(f"\n  *** SOME CHECKS FAILED ***")
    return all_pass


async def main():
    print("Step 1 E2E Test: Docker MySQL + Environment")
    print("=" * 60)

    mysql_actual = await test_mysql_connection()
    mysql_expected = {
        k: v for k, v in EXPECTED.items()
        if k in ("host", "port", "database", "pool_created")
    }
    mysql_ok = compare(mysql_expected, mysql_actual, "MySQL Connection")

    saver_actual = await test_saver()
    saver_expected = {"saver_created": True}
    saver_ok = compare(saver_expected, saver_actual, "AIOMySQLSaver")

    if mysql_ok and saver_ok:
        print(f"\n{'='*60}")
        print("  Step 1: ALL TESTS PASSED")
        print(f"{'='*60}")
        return 0
    else:
        print(f"\n{'='*60}")
        print("  Step 1: TESTS FAILED")
        print(f"{'='*60}")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
