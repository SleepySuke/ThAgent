import pytest

from harness.policy import (
    DEFAULT_NODE_POLICY,
    NODE_POLICIES,
    PolicyViolation,
    TurnBudgetExceeded,
    check_run,
    check_tool,
    check_turn,
)

POLICY = NODE_POLICIES["cr_agent"]


def test_deny_by_default_unknown_tool():
    d = check_tool(POLICY, "delete_repo", {})
    assert not d.allowed and "tool" in d.reason


def test_run_cmd_allows_whitelisted_basename():
    d = check_tool(POLICY, "run_cmd", {"cmd": ["/usr/bin/python", "-m", "pytest"]})
    assert d.allowed


def test_run_cmd_denies_non_whitelisted():
    d = check_tool(POLICY, "run_cmd", {"cmd": ["curl", "http://evil"]})
    assert not d.allowed and "curl" in d.reason


def test_run_cmd_requires_list():
    d = check_tool(POLICY, "run_cmd", {"cmd": "python -m pytest"})
    assert not d.allowed


def test_turn_budget():
    assert check_turn(POLICY, POLICY.max_turns).allowed
    d = check_turn(POLICY, POLICY.max_turns + 1)
    assert not d.allowed
    with pytest.raises(TurnBudgetExceeded):
        if not d.allowed:
            raise TurnBudgetExceeded(d.reason)


def test_check_run_unknown_node_denied():
    assert not check_run(None).allowed


def test_exceptions_are_policy_violations():
    assert issubclass(TurnBudgetExceeded, PolicyViolation)


def test_cr_agent_memory_enabled_with_kinds():
    p = NODE_POLICIES["cr_agent"]
    assert p.memory_enabled is True
    assert p.memory_kinds == frozenset(
        {"team_convention", "past_review", "knowledge"})


def test_other_nodes_memory_denied_by_default():
    from harness.policy import DEFAULT_NODE_POLICY
    assert DEFAULT_NODE_POLICY.memory_enabled is False
    assert DEFAULT_NODE_POLICY.memory_kinds == frozenset()
    # 逐一枚举：除 cr_agent 外任何节点都不得开 memory（deny-by-default）
    assert all(not p.memory_enabled
               for n, p in NODE_POLICIES.items() if n != "cr_agent")


def test_request_human_allowed_for_cr_planning_and_test_recall():
    assert "request_human" in NODE_POLICIES["cr_agent"].allowed_tools
    assert "request_human" in NODE_POLICIES["planning_agent"].allowed_tools
    assert "request_human" in NODE_POLICIES["test_recall_agent"].allowed_tools
    assert "request_human" not in NODE_POLICIES["script_agent"].allowed_tools
    assert "request_human" not in DEFAULT_NODE_POLICY.allowed_tools


def test_search_knowledge_allowed_for_cr_and_test_recall():
    assert "search_knowledge" in NODE_POLICIES["cr_agent"].allowed_tools
    assert "search_knowledge" in NODE_POLICIES["test_recall_agent"].allowed_tools
    assert "search_knowledge" not in NODE_POLICIES["script_agent"].allowed_tools
    assert "search_knowledge" not in DEFAULT_NODE_POLICY.allowed_tools


def test_search_knowledge_exemplar_pull_channel_v2c1():
    # V2c-1：exemplar 拉通道（裁定 10）——report/case 产出前检索认可范例
    assert "search_knowledge" in NODE_POLICIES["report_agent"].allowed_tools
    assert "search_knowledge" in NODE_POLICIES["case_agent"].allowed_tools
    # 独占集断言：白名单仅四节点（deny-by-default 治理面）
    assert {n for n, p in NODE_POLICIES.items()
            if "search_knowledge" in p.allowed_tools} == {
        "cr_agent", "test_recall_agent", "report_agent", "case_agent"}
