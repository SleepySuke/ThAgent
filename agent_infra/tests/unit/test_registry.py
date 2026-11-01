import pytest

from harness.registry import (
    AGENT_REGISTRY,
    is_valid_edge,
    resolve_node,
    successors,
)

AGENT_IDS = {"planning_agent", "cr_agent", "requirement_agent",
             "strategy_agent", "case_agent", "script_agent",
             "diagnose_agent", "report_agent", "test_recall_agent",
             "change_report_agent"}
PROGRAM_IDS = {"case_executor"}


def test_registry_has_all_agents():
    assert set(AGENT_REGISTRY) >= AGENT_IDS
    assert set(AGENT_REGISTRY) >= PROGRAM_IDS
    assert AGENT_REGISTRY["case_executor"]["type"] == "program"


def test_resolve_node():
    cr = resolve_node("cr_agent")
    assert cr.type == "agent"
    assert cr.url.startswith("http://")
    prog = resolve_node("case_executor")
    assert prog.type == "program"
    assert prog.handler == "execute_cases"


def test_resolve_unknown_node_raises():
    with pytest.raises(KeyError):
        resolve_node("no_such_node")


def test_successors():
    assert successors("cr_agent") == ["test_recall_agent"]
    assert successors("test_recall_agent") == ["change_report_agent", "case_agent"]  # T5
    assert successors("change_report_agent") == ["case_agent"]               # T5 新增
    assert successors("script_agent") == ["case_executor"]
    assert successors("case_executor") == ["diagnose_agent", "report_agent"]  # 八期（V1b-1）


def test_edge_validity():
    assert is_valid_edge("cr_agent", "test_recall_agent")
    assert is_valid_edge("script_agent", "case_executor")
    assert not is_valid_edge("test_recall_agent", "cr_agent")
    assert not is_valid_edge("cr_agent", "case_executor")   # 跳级仍非法
    assert not is_valid_edge("cr_agent", "script_agent")
