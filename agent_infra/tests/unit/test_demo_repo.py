import subprocess
import sys
from pathlib import Path

from fixtures.build_demo_repo import DEFECT_COMMITS, build_demo_repo

GOLDEN = Path(__file__).parents[1] / "eval" / "golden.json"


def test_build_creates_tagged_defects(tmp_path):
    repo = build_demo_repo(tmp_path / "demo_repo")
    tags = subprocess.run(["git", "-C", str(repo), "tag", "-l"],
                          capture_output=True, text=True, check=True).stdout.split()
    assert tags == [tag for tag, _, _ in DEFECT_COMMITS]


def test_defect2_breaks_tests(tmp_path):
    repo = build_demo_repo(tmp_path / "demo_repo")
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "defect-2"], check=True)
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-x", "-q"],
        cwd=repo, capture_output=True, text=True, check=False)
    assert r.returncode != 0  # 阶梯折扣改动使 test_tier_discount 失败


def test_baseline_is_clean(tmp_path):
    repo = build_demo_repo(tmp_path / "demo_repo")
    r = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "-q"],
        cwd=repo, capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stdout


def test_every_defect_commit_changes_target(tmp_path):
    """replace 静默不生效的回归防护：每个缺陷 commit 的特征串必须在场。"""
    repo = build_demo_repo(tmp_path / "demo_repo")
    marks = {
        "defect-1": ("shop/stats.py", "except:"),
        "defect-2": ("shop/pricing.py", "DISCOUNT_TIERS = {50: 0.02"),
        "defect-3": ("shop/pricing.py", "qty = abs(qty)"),
        "defect-4": ("shop/report.py", "render_order_report"),
        "defect-5": ("shop/promo.py", "return 0.30"),
    }
    for tag, (rel, needle) in marks.items():
        subprocess.run(["git", "-C", str(repo), "checkout", "-q", tag], check=True)
        assert needle in (repo / rel).read_text(), f"{tag} 未生效：{rel} 缺少 {needle!r}"


def test_defect5_promo_added(tmp_path):
    repo = build_demo_repo(tmp_path / "demo_repo")
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "defect-5"], check=True)
    assert "0.30" in (repo / "shop" / "promo.py").read_text()


def test_defect5_promo_integrated_tests_green(tmp_path):
    """二轮手术验收不变量：promo 已接入（非死代码）、不回退 d3、测试全绿。

    convention-only 缺陷的三重保证——接入消除死代码线索、叠加 d3 消除回退
    噪声、期望同步消除 consistency 线索；唯一剩余命中路径是规范召回。
    """
    repo = build_demo_repo(tmp_path / "demo_repo")
    subprocess.run(["git", "-C", str(repo), "checkout", "-q", "defect-5"], check=True)
    pricing = (repo / "shop" / "pricing.py").read_text()
    assert "promo_rate()" in pricing          # 真实接入，非死代码
    assert "qty = abs(qty)" in pricing        # 不回退 defect-3
    r = subprocess.run([sys.executable, "-m", "pytest", "tests/", "-q"],
                       cwd=repo, capture_output=True, text=True, check=False)
    assert r.returncode == 0, r.stdout        # 无测试失败线索
