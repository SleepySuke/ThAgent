"""确定性构建种子缺陷仓库：main 基线 + 5 个缺陷 commit（defect-1..5）。

用法: uv run python -m fixtures.build_demo_repo [target]
默认 target = fixtures/demo_repo（已 gitignore）。
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
from pathlib import Path

BASELINE_FILES = {
    "shop/__init__.py": "",
    "shop/pricing.py": textwrap.dedent('''\
        """定价规则：单价、折扣与订单总价。"""

        DISCOUNT_TIERS = {100: 0.05, 500: 0.10, 1000: 0.15}


        def unit_price(item: str, price_table: dict[str, float]) -> float:
            """查询单价；未知商品抛 KeyError。"""
            return price_table[item]


        def apply_discount(total: float, pct: float) -> float:
            """按百分比打折，四舍五入到分。"""
            return round(total * (1 - pct), 2)


        def tier_discount(total: float) -> float:
            """按累计金额返回阶梯折扣率。"""
            rate = 0.0
            for threshold, r in sorted(DISCOUNT_TIERS.items()):
                if total >= threshold:
                    rate = r
            return rate


        def total_price(items: list[tuple[str, int]], price_table: dict[str, float]) -> float:
            """items: [(商品, 数量)]，返回打折后总价。"""
            subtotal = sum(qty * unit_price(item, price_table) for item, qty in items)
            return apply_discount(subtotal, tier_discount(subtotal))
    '''),
    "shop/orders.py": textwrap.dedent('''\
        """订单模型与订单级统计。"""

        from shop.pricing import total_price


        def create_order(order_id: str, items: list[tuple[str, int]],
                         price_table: dict[str, float]) -> dict:
            """创建订单快照。"""
            return {"id": order_id, "items": items, "total": total_price(items, price_table)}


        def order_total(orders: list[dict]) -> float:
            """汇总订单总金额。"""
            return sum(o["total"] for o in orders)
    '''),
    "tests/test_pricing.py": textwrap.dedent('''\
        from shop.pricing import apply_discount, tier_discount, total_price

        TABLE = {"apple": 3.5, "book": 45.0, "laptop": 5999.0}


        def test_apply_discount_rounds_to_cent():
            assert apply_discount(100.0, 0.15) == 85.0
            assert apply_discount(10.009, 0.0) == 10.01


        def test_tier_discount():
            assert tier_discount(50) == 0.0
            assert tier_discount(100) == 0.05
            assert tier_discount(600) == 0.10


        def test_total_price():
            assert total_price([("apple", 2)], TABLE) == 7.0
            assert total_price([("book", 3)], TABLE) == 128.25  # 135 * 0.95
    '''),
}


def _d5_pricing() -> str:
    """defect-5 的 pricing.py：d3 版本（负数量退货处理）之上接入大促折扣。

    叠加链：基线 → d3 循环体 → promo 接入（import + total_price 取优）。
    """
    src = BASELINE_FILES["shop/pricing.py"]
    src = src.replace(
        """    subtotal = sum(qty * unit_price(item, price_table) for item, qty in items)
    return apply_discount(subtotal, tier_discount(subtotal))""",
        """    subtotal = 0
    for item, qty in items:
        if qty < 0:
            qty = abs(qty)  # 负数数量按退货处理
        subtotal += qty * unit_price(item, price_table)
    return apply_discount(subtotal, tier_discount(subtotal))""",
    )
    src = src.replace(
        "DISCOUNT_TIERS = {100: 0.05, 500: 0.10, 1000: 0.15}",
        "from shop.promo import promo_rate\n\n"
        "DISCOUNT_TIERS = {100: 0.05, 500: 0.10, 1000: 0.15}",
    )
    src = src.replace(
        '"""items: [(商品, 数量)]，返回打折后总价。"""',
        '"""items: [(商品, 数量)]，返回打折后总价（大促期间与阶梯折扣取优）。"""',
    )
    return src.replace(
        "    return apply_discount(subtotal, tier_discount(subtotal))",
        "    return apply_discount(subtotal, max(tier_discount(subtotal), promo_rate()))",
    )


# 缺陷 commit：(tag, message, {文件: 新内容}，None 值表示删除)
DEFECT_COMMITS = [
    ("defect-1", "feat: 新增订单均值统计", {
        "shop/stats.py": textwrap.dedent('''\
            """订单统计指标。"""


            def average_order_value(orders: list[dict]) -> float:
                """平均订单金额；无订单时返回 0。"""
                try:
                    return order_total(orders) / len(orders)
                except:
                    return 0
        '''),
    }),
    ("defect-2", "feat: 新增 50 元档小额折扣", {
        "shop/pricing.py": BASELINE_FILES["shop/pricing.py"].replace(
            "DISCOUNT_TIERS = {100: 0.05, 500: 0.10, 1000: 0.15}",
            "DISCOUNT_TIERS = {50: 0.02, 100: 0.05, 500: 0.10, 1000: 0.15}",
        ),
    }),
    ("defect-3", "feat: 负数数量按退货处理", {
        # 源串缩进必须与 dedent 后的基线一致（函数体 4 空格），否则 replace 静默不生效
        "shop/pricing.py": BASELINE_FILES["shop/pricing.py"].replace(
            """    subtotal = sum(qty * unit_price(item, price_table) for item, qty in items)
    return apply_discount(subtotal, tier_discount(subtotal))""",
            """    subtotal = 0
    for item, qty in items:
        if qty < 0:
            qty = abs(qty)  # 负数数量按退货处理
        subtotal += qty * unit_price(item, price_table)
    return apply_discount(subtotal, tier_discount(subtotal))""",
        ),
    }),
    ("defect-4", "feat: 订单文本报表", {
        "shop/report.py": textwrap.dedent('''\
            """订单报表（生成文本报表）。"""


            def render_order_report(orders: list[dict], price_table: dict[str, float]) -> str:
                """渲染订单报表：逐单计算小计、折扣与总计，返回文本。"""
                lines = []
                grand = 0.0
                for o in orders:
                    items = o["items"]
                    subtotal = 0.0
                    for item, qty in items:
                        price = price_table[item]
                        subtotal += qty * price
                    if subtotal >= 1000:
                        rate = 0.15
                    elif subtotal >= 500:
                        rate = 0.10
                    elif subtotal >= 100:
                        rate = 0.05
                    else:
                        rate = 0.0
                    total = round(subtotal * (1 - rate), 2)
                    grand += total
                    lines.append(f"订单 {o['id']}: 小计 {subtotal:.2f} 折扣 {rate:.0%} 应付 {total:.2f}")
                lines.append(f"总计: {grand:.2f}")
                return "\\n".join(lines)
        '''),
    }),
    ("defect-5", "feat: 大促折扣接入总价（与阶梯取优）", {
        # 二轮手术（2026-10-24）：promo 真实接入 total_price，消除"死代码"独立
        # 命中线索——A 组无记忆时唯一可报角度只剩规范违规（0.30 > 上限 0.20）。
        # promo.py 字节不动（golden 锚点 line 6 不变）；pricing 基于 d3 版本叠加
        # （直改基线会让 d4..d5 diff 携带"回退 d3"噪声，引入无关可报线索）；
        # 同步更新测试期望保持全绿（convention-only：无 consistency 线索）。
        "shop/promo.py": textwrap.dedent('''\
            """促销折扣（限时活动）。"""


            def promo_rate() -> float:
                """大促折扣率：全场统一 30% 折扣（无门槛）。"""
                return 0.30
        '''),
        "shop/pricing.py": _d5_pricing(),
        "tests/test_pricing.py": textwrap.dedent('''\
            from shop.pricing import apply_discount, tier_discount, total_price

            TABLE = {"apple": 3.5, "book": 45.0, "laptop": 5999.0}


            def test_apply_discount_rounds_to_cent():
                assert apply_discount(100.0, 0.15) == 85.0
                assert apply_discount(10.009, 0.0) == 10.01


            def test_tier_discount():
                assert tier_discount(50) == 0.0
                assert tier_discount(100) == 0.05
                assert tier_discount(600) == 0.10


            def test_total_price_promo():
                # 大促期间全场 30%（与阶梯折扣取优）
                assert total_price([("apple", 2)], TABLE) == 4.9   # 7.0 * 0.7
                assert total_price([("book", 3)], TABLE) == 94.5   # 135 * 0.7
        '''),
    }),
]


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _write(repo: Path, files: dict[str, str | None]) -> None:
    for rel, content in files.items():
        p = repo / rel
        if content is None:
            p.unlink(missing_ok=True)
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")


def build_demo_repo(target: Path) -> Path:
    if target.exists():
        subprocess.run(["rm", "-rf", str(target)], check=True)
    target.mkdir(parents=True)
    _git(target, "init", "-b", "main")
    _git(target, "config", "user.email", "fixture@example.com")
    _git(target, "config", "user.name", "fixture-builder")
    _write(target, {"README.md": "seed defect repo\n", **BASELINE_FILES})
    _git(target, "add", "-A")
    _git(target, "commit", "-m", "init: 订单计价基线")
    for tag, message, files in DEFECT_COMMITS:
        _write(target, files)
        _git(target, "add", "-A")
        _git(target, "commit", "-m", message)
        _git(target, "tag", tag)
    return target


if __name__ == "__main__":
    default = Path(__file__).parent / "demo_repo"
    build_demo_repo(Path(sys.argv[1]) if len(sys.argv) > 1 else default)
    print(f"built: {default if len(sys.argv) <= 1 else sys.argv[1]}")
