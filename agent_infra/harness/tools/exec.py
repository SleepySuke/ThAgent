"""执行类沙箱工具：read_diff / run_cmd。"""
from __future__ import annotations

from harness.tools._base import _SPECS, _wrap


def read_diff(run, session):
    @_wrap(_SPECS["read_diff"])
    async def read_diff() -> dict:
        """读取被审查 commit 相对其父提交的完整 diff（review 的主要输入）。"""
        # 同步 git diff（快）——裁定 8 sync 保留清单成员（t9-final #7）
        return {"diff": session().diff()[:20_000]}
    return read_diff


def run_cmd(run, session):
    @_wrap(_SPECS["run_cmd"])
    async def run_cmd(cmd: list[str]) -> dict:
        """在沙箱内执行白名单命令，如 ["python","-m","pytest"] 或 ["ruff","check","."]。"""
        r = await session().run(cmd)  # 沙箱层已有 timeout_s + kill（矩阵 #14）
        return {"exit_code": r.exit_code, "stdout": r.stdout,
                "stderr": r.stderr, "timed_out": r.timed_out}
    return run_cmd
