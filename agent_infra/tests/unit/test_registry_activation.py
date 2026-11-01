"""六期新链 DAG 边：合法性域 + defer 标注 + parse_plan 接受/拒绝（矩阵 #3）。"""
import json

import pytest

from harness.contract import OutputContractError, parse_plan
from harness.registry import successors

FULL_CHAIN = {"plan_id": "P8",
              "nodes": [{"id": "cr", "agent": "cr_agent"},
                        {"id": "test_recall", "agent": "test_recall_agent"},
                        {"id": "case", "agent": "case_agent"},
                        {"id": "script", "agent": "script_agent"},
                        {"id": "execute", "program": "case_executor"},
                        {"id": "report", "agent": "report_agent"}],
              "edges": [["cr", "test_recall"], ["test_recall", "case"],
                        ["case", "script"], ["script", "execute"],
                        ["execute", "report"]]}


def test_new_chain_edges_are_valid():
    from harness.registry import is_valid_edge
    assert is_valid_edge("requirement_agent", "strategy_agent")
    assert is_valid_edge("strategy_agent", "cr_agent")
    assert is_valid_edge("case_executor", "report_agent")
    assert not is_valid_edge("requirement_agent", "cr_agent")  # 跳级非法


def test_report_anchored_on_executor():
    assert successors("case_executor") == ["diagnose_agent", "report_agent"]  # 八期
    assert successors("report_agent") == []            # 收口节点无后继


def test_parse_plan_accepts_full_chain():
    plan = parse_plan(json.dumps(FULL_CHAIN))
    assert len(plan.nodes) == 6 and len(plan.edges) == 5


def test_parse_plan_rejects_skipping_strategy():  # 矩阵 #3
    bad = {"plan_id": "P",
           "nodes": [{"id": "requirement", "agent": "requirement_agent"},
                     {"id": "cr", "agent": "cr_agent"}],
           "edges": [["requirement", "cr"]]}
    with pytest.raises(OutputContractError, match="not in DAG"):
        parse_plan(json.dumps(bad))
