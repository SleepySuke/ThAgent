"""集成：case_executor 的 cover_ratio 比对与 WARN（矩阵 #4）。"""
import json

from harness.programs.case_executor import COVER_WARN, execute_cases

SCRIPT_FULL = """# TC-101 generate
def test_tc_101():
    assert True


# TC-002 reuse: tests/test_pricing.py::test_tier_discount
def test_tc_002():
    assert True
"""
CASES = {"case_list": [
    {"id": "TC-101", "scenario": "s1", "action": "generate", "src": "",
     "linked_risk": "r1"},
    {"id": "TC-002", "scenario": "s2", "action": "reuse",
     "src": "tests/test_pricing.py::test_tier_discount", "linked_risk": "r2"}],
    "summary": "2"}


def _mk_run(tmp_path, script: str | None, cases: dict | None):
    # exist_ok：同测试内两次造 run（半覆盖/零覆盖对照）不炸（brief 原文缺此参）
    run = tmp_path / "r"
    (run / "sandbox").mkdir(parents=True, exist_ok=True)
    (run / "artifacts").mkdir(exist_ok=True)
    if script is not None:
        (run / "sandbox" / "test_cases.py").write_text(script, encoding="utf-8")
    if cases is not None:
        (run / "artifacts" / "case_list.json").write_text(
            json.dumps(cases, ensure_ascii=False), encoding="utf-8")
    return run


def test_cover_ratio_full_no_warn(tmp_path):
    _mk_run(tmp_path, SCRIPT_FULL, CASES)
    out = execute_cases(tmp_path, "r", [])
    assert out["cover_ratio"] == 1.0
    assert "WARN" not in out["stdout"]


def test_cover_ratio_partial_warns_but_not_blocks(tmp_path):   # 矩阵 #4
    assert COVER_WARN == 0.5                          # 阈值钉桩（低于才 WARN）
    script = SCRIPT_FULL.replace("# TC-101 generate", "")   # 漏掉 TC-101 → 0.5
    _mk_run(tmp_path, script, CASES)
    out = execute_cases(tmp_path, "r", [])
    assert out["cover_ratio"] == 0.5
    assert "WARN" not in out["stdout"]                  # 0.5 不低于阈值不告警
    script2 = "# 只有无关内容\ndef test_other():\n    assert True\n"
    _mk_run(tmp_path, script2, CASES)
    out2 = execute_cases(tmp_path, "r", [])
    assert out2["cover_ratio"] == 0.0
    assert "WARN" in out2["stdout"] and "cover_ratio" in out2["stdout"]
    assert out2["exit_code"] == 0                       # WARN 不阻断（必过脚本）


def test_cover_ratio_absent_without_case_list(tmp_path):       # 旧链兼容
    _mk_run(tmp_path, "def test_ok():\n    assert True\n", None)
    out = execute_cases(tmp_path, "r", [])
    assert "cover_ratio" not in out                     # 不算键不罚
