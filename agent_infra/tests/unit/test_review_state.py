"""九期裁定 1：REVIEW_PENDING 状态与三出边 + 旧转换全保留回归。"""
import pytest

from harness.state import HarnessState, InvalidTransition, StateMachine


def _to_executing() -> StateMachine:
    sm = StateMachine()
    sm.transition("SUBMIT_TASK")
    sm.transition("PLAN_READY")
    return sm


def test_executing_submits_review():
    sm = _to_executing()
    assert sm.transition("SUBMIT_REVIEW") is HarnessState.REVIEW_PENDING


def test_review_accept_completes():
    sm = _to_executing()
    sm.transition("SUBMIT_REVIEW")
    assert sm.transition("REVIEW_ACCEPT") is HarnessState.COMPLETED


def test_review_reject_returns_to_planning():
    sm = _to_executing()
    sm.transition("SUBMIT_REVIEW")
    assert sm.transition("REVIEW_REJECT") is HarnessState.PLANNING


def test_review_cancel():
    sm = _to_executing()
    sm.transition("SUBMIT_REVIEW")
    assert sm.transition("CANCEL") is HarnessState.CANCELLED


def test_review_pending_has_no_error_edge():
    sm = _to_executing()
    sm.transition("SUBMIT_REVIEW")
    with pytest.raises(InvalidTransition):
        sm.transition("ERROR")  # 审阅态无 ERROR 出边（失败语义止于执行态）


def test_old_transitions_preserved():
    # 回归：一期单 cr 路径不变——ALL_STEPS_DONE→COMPLETED 仍在
    sm = _to_executing()
    assert sm.transition("ALL_STEPS_DONE") is HarnessState.COMPLETED
    sm2 = _to_executing()
    assert sm2.transition("EXECUTE_AGENT") is HarnessState.EXECUTING
    assert sm2.transition("NEED_HUMAN_INPUT") is HarnessState.PAUSED
    assert sm2.transition("RESUME") is HarnessState.EXECUTING
    assert sm2.transition("ERROR") is HarnessState.FAILED
