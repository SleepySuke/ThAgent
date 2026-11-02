"""L 层：Checkpoint 打点 + Crash Recovery 扫描。

四个时机打点（规划完成/节点执行前/节点完成/失败），落 runs/<rid>/checkpoint.json。
Crash Recovery：扫描有 checkpoint 但无 run_end 的 run（进程中断留下），返回
可恢复列表。idempotency_key = run_id:node_id:logical_attempt 随 A2A task 下发，
重试不重复副作用。
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Checkpoint:
    run_id: str
    context_id: str
    current_node: str | None
    harness_state: str
    completed_nodes: list[str] = field(default_factory=list)
    node_outputs: dict = field(default_factory=dict)
    round: int = 1  # 九期：审阅 replan 轮次（round>1 = reject 后的新一轮）
    version: int = 2
    created_at: float = field(default_factory=time.time)


def idempotency_key(run_id: str, node_id: str, attempt: int) -> str:
    return f"{run_id}:{node_id}:{attempt}"


def checkpoint_path(runs_root: Path, run_id: str) -> Path:
    return Path(runs_root) / run_id / "checkpoint.json"


def save_checkpoint(runs_root: Path, run_id: str, data: dict) -> None:
    p = checkpoint_path(runs_root, run_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_checkpoint(runs_root: Path, run_id: str) -> dict | None:
    p = checkpoint_path(runs_root, run_id)
    if not p.exists():
        return None
    cp = json.loads(p.read_text(encoding="utf-8"))
    # 兼容读取（裁定 6）：version 1 旧 checkpoint 无 round 键 → 默认 1
    cp.setdefault("round", 1)
    return cp


def recover_interrupted(runs_root: Path) -> list[dict]:
    """扫描有 checkpoint 但无 run_end 的 run（进程中断留下），返回可恢复列表。

    # ponytail: 只扫描报告；真正 resume（读 checkpoint → 续跑）是 engine 侧
    # execute_for 复用 checkpoint 的接缝，这里不硬编码恢复策略。
    """
    root = Path(runs_root)
    interrupted: list[dict] = []
    if not root.exists():
        return interrupted
    for run_dir in sorted(root.iterdir()):
        if not run_dir.is_dir():
            continue
        cp = load_checkpoint(root, run_dir.name)
        if cp is None or _run_ended(run_dir):
            continue
        interrupted.append({"run_id": run_dir.name, "checkpoint": cp})
    return interrupted


def _run_ended(run_dir: Path) -> bool:
    trace = run_dir / "trace.jsonl"
    if not trace.exists():
        return False
    for line in trace.read_text(encoding="utf-8").splitlines():
        try:
            if json.loads(line).get("event") == "run_end":
                return True
        except json.JSONDecodeError:
            continue
    return False
