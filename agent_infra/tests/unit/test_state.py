import pytest

from harness.state import HarnessState, InvalidTransition, StateMachine


def test_valid_transition_planning():
    sm = StateMachine()
    assert sm.transition("SUBMIT_TASK") is HarnessState.PLANNING
    assert sm.transition("PLAN_READY") is HarnessState.EXECUTING


def test_invalid_transition_raises():
    sm = StateMachine()
    with pytest.raises(InvalidTransition):
        sm.transition("PLAN_READY")  # IDLE 不接受 PLAN_READY
    sm.transition("SUBMIT_TASK")
    with pytest.raises(InvalidTransition):
        sm.transition("SUBMIT_TASK")  # PLANNING 不接受重复 SUBMIT_TASK


def test_terminal_states():
    sm = StateMachine()
    sm.transition("SUBMIT_TASK")
    sm.transition("PLAN_READY")
    sm.transition("ALL_STEPS_DONE")
    assert sm.state is HarnessState.COMPLETED
    with pytest.raises(InvalidTransition):
        sm.transition("RETRY")  # COMPLETED 不可再转

    sm2 = StateMachine()
    sm2.transition("SUBMIT_TASK")
    sm2.transition("CANCEL")
    assert sm2.state is HarnessState.CANCELLED
    with pytest.raises(InvalidTransition):
        sm2.transition("RESTORE")  # CANCELLED 不可再转


def test_failed_is_recoverable():
    # 设计 §7：FAILED 可 RETRY/REPLAN（Task 11 重试依赖此路径）
    sm = StateMachine()
    sm.transition("SUBMIT_TASK")
    sm.transition("PLAN_READY")
    sm.transition("ERROR")
    assert sm.state is HarnessState.FAILED
    assert sm.transition("RETRY") is HarnessState.EXECUTING
    sm.transition("ERROR")
    assert sm.transition("REPLAN") is HarnessState.PLANNING


def test_interrupted_restore():
    sm = StateMachine()
    sm.transition("SUBMIT_TASK")
    sm.transition("PLAN_READY")
    sm.transition("INTERRUPT")
    assert sm.state is HarnessState.INTERRUPTED
    assert sm.transition("RESTORE") is HarnessState.EXECUTING
