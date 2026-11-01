"""T 层：共享沙箱工具注册与组装。

每个 agent 在 build_agent 里用 `build_tools(run, manager, names=[...])` 显式声明
自己的工具面（LLM 只看到自己的工具，不靠运行期意图识别去调用）。agent 专属
工具放 `agents/<agent>/` 下各自组装，不塞进这里。

共享工具按职责分文件：files（读/写/列）、exec（diff/命令）、artifact（产物读）。
"""
from __future__ import annotations

from collections.abc import Callable

from harness.contract import RunContext
from harness.sandbox.manager import SandboxManager
from harness.tools._base import make_session
from harness.tools.artifact import read_artifact
from harness.tools.exec import read_diff, run_cmd
from harness.tools.files import list_files, read_file, write_file
from harness.tools.hitl import request_human
from harness.tools.knowledge import search_knowledge

# 工具名 → 工厂（工厂签名：fn(run, session) -> tool_callable）
FACTORIES: dict[str, Callable] = {
    "read_diff": read_diff,
    "read_file": read_file,
    "write_file": write_file,
    "list_files": list_files,
    "run_cmd": run_cmd,
    "read_artifact": read_artifact,
    "request_human": request_human,
    "search_knowledge": search_knowledge,
}


def build_tools(run: RunContext, manager: SandboxManager,
                names: list[str]) -> list[Callable]:
    """按 names 组装工具子集（agent 显式声明自己的工具面）。"""
    session = make_session(run, manager)
    return [FACTORIES[n](run, session) for n in names]
