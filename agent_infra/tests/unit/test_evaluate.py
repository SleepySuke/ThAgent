from eval.evaluate import evaluate_commit, evaluate_report, load_golden, match_issue

G = {"file": "shop/stats.py", "line": 8, "type": "exception"}
A_HIT = {"file": "shop/stats.py", "line": 10, "type": "exception"}


def test_match_issue_line_tolerance():
    assert match_issue(G, A_HIT)
    assert not match_issue(G, {**A_HIT, "line": 20})
    # type 不做硬条件：位置命中而分类口径不同仍算审对
    assert match_issue(G, {**A_HIT, "type": "bug"})
    # 行号容差 6：函数头 vs 逻辑行的定位差（e2e 实测 defect-4 差 6 行）
    assert match_issue(G, {**A_HIT, "line": 14})
    assert not match_issue(G, {**A_HIT, "line": 15})
    assert not match_issue(G, {**A_HIT, "file": "shop/other.py"})


def test_match_issue_alt_files():
    # 替代锚点是 file 级匹配：报进该文件即算找对地方（行号只对主锚点生效）
    g = {"file": "shop/pricing.py", "line": 3, "alt_files": ["tests/test_pricing.py"]}
    assert match_issue(g, {"file": "tests/test_pricing.py", "line": 12})
    assert match_issue(g, {"file": "shop/pricing.py", "line": 3})
    assert not match_issue(g, {"file": "tests/test_x.py", "line": 3})   # 非替代锚点
    assert not match_issue(g, {"file": "shop/pricing.py", "line": 20})  # 主锚点越容差


def test_evaluate_commit_counts():
    golden = {"issues": [G], "verdict": "request_changes"}
    actual = {"issues": [A_HIT, {"file": "shop/x.py", "line": 1,
                                  "type": "bug", "severity": "high",
                                  "desc": "d"}],
              "verdict": "request_changes"}
    r = evaluate_commit(golden, actual)
    assert r["hits"] == 1 and r["misses"] == 0
    assert len(r["false_positives"]) == 1 and r["verdict_ok"]


def test_evaluate_report_aggregates():
    golden_all = {"defect-1": {"issues": [G], "verdict": "request_changes"}}
    reports = {"defect-1": {"issues": [A_HIT], "verdict": "request_changes"}}
    r = evaluate_report(golden_all, reports)
    assert r["total_hit_rate"] == 1.0
    assert r["verdict_accuracy"] == 1.0
    assert set(r["per_commit"]) == {"defect-1"}


def test_golden_file_loads():
    golden = load_golden()
    assert set(golden) == {"defect-1", "defect-2", "defect-3", "defect-4",
                           "defect-5"}
    assert all("issues" in v and "verdict" in v for v in golden.values())


def test_golden_includes_defect_5():
    golden = load_golden()
    assert "defect-5" in golden
    assert golden["defect-5"]["issues"][0]["file"] == "shop/promo.py"
