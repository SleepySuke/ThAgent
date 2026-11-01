"""artifacts 目录读取工具（worktree 之外）。"""
from __future__ import annotations

from pathlib import Path

from harness.tools._base import _SPECS, _wrap


def read_artifact(run, session):
    @_wrap(_SPECS["read_artifact"])
    async def read_artifact(path: str) -> dict:
        """读取本 run 的 artifacts 目录下文件（如上游产出的 cr_report.json）。

        path 为相对 artifacts 目录的路径；artifacts 目录在 worktree 之外
        （runs/<rid>/artifacts/），故独立于沙箱 read_file 的 jail，但同样
        限制在 artifacts 目录内，不许越界。
        """
        base = Path(run.artifacts_dir).resolve()
        if not run.artifacts_dir or not base.is_dir():
            return {"error": "artifacts dir not available"}
        p = (base / path).resolve()
        if base != p and base not in p.parents:
            return {"error": f"path escapes artifacts dir: {path}"}
        return {"content": p.read_text(encoding="utf-8", errors="replace")}
    return read_artifact
