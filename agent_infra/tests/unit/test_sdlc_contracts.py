"""八期新节点 _FINALIZE 契约单测（agent_server 的 parse 函数族）。"""
import json

import pytest

from agent_server import (
    _FINALIZE,
    _parse_case_list,
    _parse_change_report,
    _parse_recall,
    _parse_report,
    _parse_script,
)
from eval.evaluate import load_golden
from harness.contract import OutputContractError

RECALL_OK = ('{"recalled": [{"case_id": "TC-002", "source": "test-cases.md",'
             ' "score": 0.8, "matched_risk": "档位变更"}], '
             '"gaps": [{"risk": "负数数量", "reason": "检索无命中"}], '
             '"recall_stats": {"queries": 2, "skipped": 0, "hits": 1},'
             ' "summary": "召回 1 缺 1"}')


def test_parse_recall_accepts_valid_contract():
    d = _parse_recall(RECALL_OK)
    assert d["recalled"][0]["case_id"] == "TC-002"
    assert d["recall_stats"]["hits"] == 1


@pytest.mark.parametrize("bad", [
    '{"recalled": "not-a-list", "gaps": [], "recall_stats": {}}',   # recalled 非 list
    '{"recalled": [], "gaps": 42, "recall_stats": {}}',             # gaps 非 list
    '{"recalled": [], "gaps": []}',                                 # 缺 recall_stats
])
def test_parse_recall_rejects_malformed(bad):
    with pytest.raises(OutputContractError):
        _parse_recall(bad)


def test_finalize_maps_test_recall():
    parse_fn, artifact = _FINALIZE["test_recall_agent"]
    assert artifact == "test_recall"                # 落 artifacts/test_recall.json
    assert parse_fn is _parse_recall


CASE_OK = ('{"case_list": ['
           '{"id": "TC-101", "scenario": "负数数量退货", "action": "generate",'
           ' "src": "", "linked_risk": "abs 转正"},'
           '{"id": "TC-002", "scenario": "档位边界", "action": "reuse",'
           ' "src": "tests/test_pricing.py::test_tier_discount",'
           ' "linked_risk": "档位变更"}], "summary": "2 条"}')


def test_parse_case_list_accepts_valid():
    d = _parse_case_list(CASE_OK)
    assert [c["action"] for c in d["case_list"]] == ["generate", "reuse"]


def test_parse_case_list_rejects_malformed():
    import json
    bad_cases = [
        json.dumps({"case_list": [{"id": "TC-1", "scenario": "s",
                                   "action": "maybe", "src": "",
                                   "linked_risk": "r"}]}),            # action 出域
        json.dumps({"case_list": [{"id": "TC-1", "scenario": "s",
                                   "action": "reuse", "src": "a",
                                   "linked_risk": "r"},
                                  {"id": "TC-1", "scenario": "s2",
                                   "action": "reuse", "src": "b",
                                   "linked_risk": "r2"}]}),            # id 重复
        json.dumps({"case_list": [{"id": "TC-1", "action": "reuse"}]}),  # 缺键
    ]
    for bad in bad_cases:
        with pytest.raises(OutputContractError):
            _parse_case_list(bad)


def test_finalize_maps_case_agent():
    parse_fn, artifact = _FINALIZE["case_agent"]
    assert artifact == "case_list"                 # 落 artifacts/case_list.json
    assert parse_fn is _parse_case_list


def test_parse_case_list_accepts_empty():
    # 无风险输入的诚实降级：空清单合法（与 _parse_recall 空 recalled 同惯例）
    data = _parse_case_list(
        json.dumps({"case_list": [], "summary": "无风险输入，清单为空"}))
    assert data["case_list"] == []


def test_finalize_maps_script_and_testing_retired():
    parse_fn, artifact = _FINALIZE["script_agent"]
    assert parse_fn is _parse_script                    # 脚本文本原样收（非 JSON）
    assert artifact == "test_cases"                     # executor 读 sandbox 脚本不变
    assert "testing_agent" not in _FINALIZE             # 退役（V1b-7 对偶）


def test_golden_evolved_to_new_chain():                 # V1a-1 形状钉桩
    for tag, entry in load_golden().items():
        assert entry["expect_nodes"] == [
            "cr_agent", "test_recall_agent", "change_report_agent",
            "case_agent", "script_agent", "case_executor",
            "report_agent"], tag   # 7 节点默认链（终审 Critical：对齐 planning 教学）
        assert entry["must_use"]["test_recall_agent"] == ["search_knowledge"]
        assert entry["must_use"]["script_agent"] == ["read_artifact", "write_file"]
        assert entry["expect_test"] is True and entry["issues"], tag   # 旧键零改动


CHANGE_OK =('{"summary": "s", "risk_n": 2, "recalled_n": 1, "recommended_n": 2,'
             ' "markdown": "# 变更分析报告\\n该测什么"}')
EXEC_OK = ('{"summary": "s", "verdicts": [{"node": "cr_agent", "verdict": "approve"}],'
           ' "stats": {"issues": 1, "tests_passed": 3, "tests_total": 5,'
           ' "pass_rate": 0.6}, "root_causes_n": 0,'
           ' "markdown": "# 执行报告\\n测得怎样"}')


def test_parse_change_report_valid_and_malformed():
    assert _parse_change_report(CHANGE_OK)["recalled_n"] == 1
    for bad in ('{"summary": "s", "risk_n": "2", "recalled_n": 1,'
                ' "recommended_n": 2, "markdown": "m"}',          # risk_n 非 int
                '{"summary": "", "risk_n": 1, "recalled_n": 1,'
                ' "recommended_n": 1, "markdown": "m"}',          # 空 summary
                '{"summary": "s", "risk_n": 1, "recalled_n": 1,'
                ' "recommended_n": 1, "markdown": "  "}'):        # 空 markdown
        with pytest.raises(OutputContractError):
            _parse_change_report(bad)


def test_parse_report_accepts_execution_contract():
    d = _parse_report(EXEC_OK)
    assert d["stats"]["pass_rate"] == 0.6 and d["root_causes_n"] == 0


def test_finalize_dual_report_artifact_names():   # 矩阵 #11
    assert _FINALIZE["change_report_agent"][1] == "change_report.md"
    assert _FINALIZE["report_agent"][1] == "execution_report.md"


from agent_server import _parse_diagnose  # noqa: E402

DIAG_OK = ('{"root_causes": [{"case": "test_tc_101", "cause": "abs 转正",'
           ' "evidence": "shop/pricing.py:30"}], "summary": "定位 1 条"}')


def test_parse_diagnose_valid_empty_and_malformed():
    assert _parse_diagnose(DIAG_OK)["root_causes"][0]["case"] == "test_tc_101"
    empty = '{"root_causes": [], "summary": "无失败用例"}'   # 矩阵 #7 合法空
    assert _parse_diagnose(empty)["root_causes"] == []
    for bad in ('{"root_causes": [], "summary": ""}',            # 空 summary
                '{"root_causes": "x", "summary": "s"}',          # 非 list
                '{"root_causes": [{"case": "c"}], "summary": "s"}'):  # 缺键
        with pytest.raises(OutputContractError):
            _parse_diagnose(bad)


def test_finalize_maps_diagnose():
    parse_fn, artifact = _FINALIZE["diagnose_agent"]
    assert parse_fn is _parse_diagnose               # 落 artifacts/diagnose.json
    assert artifact == "diagnose"
