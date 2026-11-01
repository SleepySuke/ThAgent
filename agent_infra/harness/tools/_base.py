"""沙箱工具共享底座：ToolSpec 声明表 + 统一包装器 + 惰性会话工厂。

各工具文件（files/exec/artifact/knowledge/hitl）从这里 import `_wrap` 与
`_SPECS`；`make_session` 提供"首次工具调用才创建沙箱"的惰性语义（对 LLM
透明，与 sandbox_destroy 成对），并在 attempt>1 时先 reset 回干净态。
"""
from __future__ import annotations

import asyncio
import functools
from collections.abc import Callable
from dataclasses import dataclass

from harness.contract import RunContext
from harness.sandbox.base import SandboxSpec
from harness.sandbox.manager import SandboxManager


@dataclass(frozen=True)
class ToolSpec:
    name: str
    kind: str                    # read | write | exec | network | hitl
    deadline_s: float | None = None   # network/exec 必填（矩阵 #15 批屏障治理）
    max_result_chars: int = 20_000


# 共享工具声明表（治理面）：新增工具漏声明即被 test_specs_cover_all_factories 钉红
_SPECS: dict[str, ToolSpec] = {
    "read_file": ToolSpec("read_file", "read"),
    "write_file": ToolSpec("write_file", "write"),
    "list_files": ToolSpec("list_files", "read"),
    "read_diff": ToolSpec("read_diff", "read"),
    "run_cmd": ToolSpec("run_cmd", "exec", deadline_s=None),  # 沙箱 timeout_s 已限，不双限
    "read_artifact": ToolSpec("read_artifact", "read"),
    "search_knowledge": ToolSpec("search_knowledge", "network", deadline_s=30.0),
    "request_human": ToolSpec("request_human", "hitl"),       # 无 deadline：等人语义
}


def _cap(out: object, max_chars: int) -> object:
    """dict 内 str 值超限截断 + truncated 标志（防上下文爆炸，矩阵 #15）。"""
    if not isinstance(out, dict):
        return out
    truncated = False
    capped: dict = {}
    for k, v in out.items():
        if isinstance(v, str) and len(v) > max_chars:
            capped[k] = v[:max_chars]
            truncated = True
        else:
            capped[k] = v
    if truncated:
        capped["truncated"] = True
    return capped


def _wrap(spec: ToolSpec):
    """统一包装器（_guard 升级为原生 async）：deadline / 结果 cap / 错误分型。

    错误形状 {"error": {"kind": timeout|limit|denied|exec_failed, "message": str}}
    ——顶层含 "error" 键保住前端 glyph regex 与 smoke 消费方（坑 #18 后向兼容）。
    wraps 保留签名供 ADK 声明参数（内层函数名 == 工具名 == 白名单，坑 #17）。
    """
    def deco(fn):
        @functools.wraps(fn)
        async def wrapper(*args, **kwargs):
            try:
                call = fn(*args, **kwargs)
                if spec.deadline_s is not None:
                    out = await asyncio.wait_for(call, spec.deadline_s)
                else:
                    out = await call
            except TimeoutError:
                return {"error": {"kind": "timeout",
                                  "message": f"{spec.name} deadline {spec.deadline_s}s"}}
            except Exception as e:
                return {"error": {"kind": "exec_failed", "message": str(e)}}
            return _cap(out, spec.max_result_chars)
        return wrapper
    return deco


def make_session(run: RunContext, manager: SandboxManager) -> Callable[[], object]:
    spec = SandboxSpec(repo_path=run.repo_path, commit=run.commit)
    created = False

    def session():
        nonlocal created
        if not created:  # 惰性创建点：首个工具调用；与 sandbox_destroy 成对
            if run.attempt > 1:  # 矩阵 #16：重试轮先清上一轮副作用（幂等）
                manager.reset(run.trace_id, spec)
                run.event_sink("sandbox_reset", {"attempt": run.attempt})
            run.event_sink("sandbox_create",
                           {"commit": run.commit, "repo": run.repo_path})
            # created 后置到 get 成功：reset/create 中途抛错则下次调用重走
            # 本分支（事件不丢、脏沙箱不被静默复用——t3-rev Minor #3）
            created = True
        return manager.get(run.trace_id, spec)

    return session
