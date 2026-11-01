"""P 层：Program 节点（确定性，非 LLM）本地 handler 分发。

handler 签名：fn(runs_root: Path, run_id: str, artifact_refs: list) -> dict。
注册方式：在 harness/programs/ 下建模块，import 到本包即完成注册（见
case_executor.py）。与 Agent 节点相反，Program 节点在 harness 进程内执行，
不经过 A2A——「生成靠智能，执行靠确定性」。
"""
from __future__ import annotations

PROGRAM_HANDLERS: dict[str, object] = {}

# 注册内置 program 节点（import 即注册，engine 只按名查 dict）
from harness.programs import case_executor  # noqa: E402,F401
