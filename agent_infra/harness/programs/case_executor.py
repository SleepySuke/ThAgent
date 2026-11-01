"""case_executor：确定性执行 script_agent 生成的 pytest 脚本。

Program 节点（非 LLM），在 harness 进程内跑，不经过 A2A。固定脚本：
在 per-run 共享 worktree（runs/<run_id>/sandbox）内 `python -m pytest` 跑
script agent 经 write_file 落盘的 test_cases.py，收集 stdout/exit_code，
并按 case_list 比对 id 覆盖率（cover_ratio，低覆盖 WARN 不阻断）。

# ponytail: 直接 subprocess 在 worktree 目录跑——Program 节点是固定可信脚本，
# 不走 agent 的白名单/caging（那是防 LLM 幻觉的治理面，这里不需要）。
# artifact_refs 保留在签名里（契约对齐），当前脚本名固定 test_cases.py。
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from harness.programs import PROGRAM_HANDLERS

DEFAULT_SCRIPT = "test_cases.py"

COVER_WARN = 0.5   # 覆盖率告警阈值（矩阵 #4：WARN 不阻断）


def _cover_ratio(runs_root: Path, run_id: str) -> float | None:
    """case_list ↔ 脚本的 id 覆盖比对（矩阵 #4）。

    id 形如 TC-101 在脚本文本中唯一可搜（函数名/注释），子串匹配足够。
    case_list.json 或脚本缺失 → None（不算键不罚——兼容无 case 节点的旧链）。
    """
    case_file = Path(runs_root) / run_id / "artifacts" / "case_list.json"
    script_file = Path(runs_root) / run_id / "sandbox" / DEFAULT_SCRIPT
    if not case_file.exists() or not script_file.exists():
        return None
    cases = json.loads(case_file.read_text(encoding="utf-8")).get("case_list", [])
    if not cases:
        return None
    text = script_file.read_text(encoding="utf-8")
    hit = sum(1 for c in cases if c.get("id") and str(c["id"]) in text)
    return hit / len(cases)


def _tail(text: str, keep: int = 400) -> str:
    """stdout/stderr 瘦身：失败详情在尾部，只留尾段（含换行裁齐到行首）。"""
    text = text or ""
    if len(text) <= keep:
        return text
    cut = text[-keep:]
    nl = cut.find("\n")
    return cut[nl + 1:] if 0 <= nl < len(cut) - 1 else cut


def execute_cases(runs_root: Path, run_id: str, artifact_refs: list) -> dict:
    """在沙箱 worktree 内执行生成的 pytest 脚本，返回 exit_code/stdout/stderr。

    脚本缺失抛 ValueError（编排配置错，早暴露）。
    """
    worktree = Path(runs_root) / run_id / "sandbox"
    script = worktree / DEFAULT_SCRIPT
    if not script.exists():
        raise ValueError(f"test script not found: {script}")
    try:
        r = subprocess.run(
            ["python", "-m", "pytest", "-q", DEFAULT_SCRIPT],
            cwd=worktree, capture_output=True, text=True, timeout=120, check=False)
    except subprocess.TimeoutExpired as e:
        out = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        return {"exit_code": 124, "stdout": _tail(out), "stderr": "pytest timed out"}
    # ponytail: exit_code 必须首键 + stdout 只留尾段——upstream 500 字截断保序
    # 依赖首键；pytest 失败详情（FAILED/断言差异）在尾部，全量塞会把 diagnose
    # 的证据面挤出 head（八期终审 Important#3 实测：evidence 归属失真）
    out = {"exit_code": r.returncode, "stdout": _tail(r.stdout),
           "stderr": _tail(r.stderr)}
    ratio = _cover_ratio(runs_root, run_id)
    if ratio is not None:
        out["cover_ratio"] = ratio
        if ratio < COVER_WARN:
            out["stdout"] += (f"\nWARN: cover_ratio={ratio:.2f} < {COVER_WARN}"
                              " (case_list 与脚本覆盖不一致)")
    return out


PROGRAM_HANDLERS["execute_cases"] = execute_cases
