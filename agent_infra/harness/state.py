"""L 层：全局 Harness 状态机（9 状态 + 转换表）。

Runtime 属 Harness 层：状态机是全局运行时的权威，每次转换发 trace
`state_transition`（from→to + 触发事件）。转换表即设计 §7 的唯一事实源。
REVIEW_PENDING 与 PAUSED 相区分：等人的是「裁决」（报告 accept/reject），
不是「答案」（执行中打断续答）。

# ponytail: 事件用字符串不用枚举——状态是强类型（调试/误用即抛），
# 事件是开放式接口（planning/executor 新增事件不必改状态机）。
"""
from __future__ import annotations

from enum import StrEnum


class HarnessState(StrEnum):
    IDLE = "idle"
    PLANNING = "planning"
    EXECUTING = "executing"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INTERRUPTED = "interrupted"
    REVIEW_PENDING = "review_pending"


class InvalidTransition(RuntimeError):
    """非法状态转换（状态机拒绝，通常意味编排 bug）。"""


# 转换表：state -> {event -> next_state}
# COMPLETED / CANCELLED 是严格终态（无出边）；FAILED 可 RETRY/REPLAN（可恢复）。
_TRANSITIONS: dict[HarnessState, dict[str, HarnessState]] = {
    HarnessState.IDLE: {"SUBMIT_TASK": HarnessState.PLANNING},
    HarnessState.PLANNING: {
        "PLAN_READY": HarnessState.EXECUTING,
        "ERROR": HarnessState.FAILED,
        "CANCEL": HarnessState.CANCELLED,
    },
    HarnessState.EXECUTING: {
        "EXECUTE_AGENT": HarnessState.EXECUTING,
        "EXECUTE_PROGRAM": HarnessState.EXECUTING,
        "NEED_HUMAN_INPUT": HarnessState.PAUSED,
        "ALL_STEPS_DONE": HarnessState.COMPLETED,
        "SUBMIT_REVIEW": HarnessState.REVIEW_PENDING,
        "ERROR": HarnessState.FAILED,
        "CANCEL": HarnessState.CANCELLED,
        "INTERRUPT": HarnessState.INTERRUPTED,
    },
    # 发 SUBMIT_REVIEW 还是 ALL_STEPS_DONE 由 engine 决定（plan 含 report 且
    # 非 auto → SUBMIT_REVIEW）；状态机保持单值转换表（裁定 1）
    HarnessState.REVIEW_PENDING: {
        # CANCEL 出边当前无 engine 发射路径（park 期间 body 已 done，pause_run
        # 返回 False）——保留是给 Task 5 的 review API（裁决动作可扩 cancel）或
        # Task 9 终审裁定的占位；状态机完备性优先于可达性（t4-rev Minor #3）
        "REVIEW_ACCEPT": HarnessState.COMPLETED,
        "REVIEW_REJECT": HarnessState.PLANNING,
        "CANCEL": HarnessState.CANCELLED,
    },
    HarnessState.PAUSED: {
        "RESUME": HarnessState.EXECUTING,
        "CANCEL": HarnessState.CANCELLED,
        "ERROR": HarnessState.FAILED,
    },
    HarnessState.FAILED: {
        "RETRY": HarnessState.EXECUTING,
        "REPLAN": HarnessState.PLANNING,
    },
    HarnessState.INTERRUPTED: {"RESTORE": HarnessState.EXECUTING},
}


class StateMachine:
    def __init__(self, initial: HarnessState = HarnessState.IDLE) -> None:
        self.state = initial

    def transition(self, event: str) -> HarnessState:
        table = _TRANSITIONS.get(self.state, {})
        if event not in table:
            raise InvalidTransition(
                f"invalid transition: {self.state.value} --{event}--> ?")
        self.state = table[event]
        return self.state
