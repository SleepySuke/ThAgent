"""沙箱工具共享底座：异常守卫 + 惰性会话工厂。

各工具文件（files/exec/artifact）从这里 import `_guard`；`make_session` 提供
"首次工具调用才创建沙箱"的惰性语义（对 LLM 透明，与 sandbox_destroy 成对）。
"""
from __future__ import annotations

import functools
from collections.abc import Callable

from harness.contract import RunContext
from harness.sandbox.base import SandboxSpec
from harness.sandbox.manager import SandboxManager


def _guard(fn):
    """沙箱异常转 error dict，不打断 agent。wraps 保留签名供 ADK 声明参数。"""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            return {"error": str(e)}
    return wrapper


def make_session(run: RunContext, manager: SandboxManager) -> Callable[[], object]:
    spec = SandboxSpec(repo_path=run.repo_path, commit=run.commit)
    created = False

    def session():
        nonlocal created
        if not created:  # 惰性创建点：首个工具调用；与 sandbox_destroy 成对
            created = True
            run.event_sink("sandbox_create",
                           {"commit": run.commit, "repo": run.repo_path})
        return manager.get(run.trace_id, spec)

    return session
