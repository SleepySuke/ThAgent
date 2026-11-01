"""E 层：沙箱抽象。接口不泄露 worktree 细节，docker/gVisor/E2B 作为新 Provider 接入。"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


class SandboxError(RuntimeError):
    pass


class SandboxEscapeError(SandboxError):
    """路径越出沙箱边界。"""


class SandboxLimitError(SandboxError):
    """会话级资源上限触发。"""


@dataclass
class ResourceLimits:
    timeout_s: int = 120            # 单命令墙钟
    max_output_bytes: int = 64_000  # 单命令输出截断（防上下文爆炸）
    max_total_cmds: int = 40        # 会话级命令数上限


@dataclass
class CmdResult:
    cmd: list[str]
    exit_code: int
    stdout: str
    stderr: str
    truncated: bool = False
    timed_out: bool = False


@dataclass
class SandboxSpec:
    repo_path: str
    commit: str
    limits: ResourceLimits = field(default_factory=ResourceLimits)


@dataclass
class Artifact:
    path: str


class SandboxSession(Protocol):
    async def run(self, cmd: list[str]) -> CmdResult: ...
    def read_file(self, path: str) -> str: ...
    def write_file(self, path: str, content: str) -> None: ...
    def list_files(self, prefix: str = "") -> list[str]: ...
    def diff(self) -> str: ...
    def snapshot(self, artifacts_dir: Path) -> Artifact: ...
    def destroy(self) -> None: ...


class SandboxProvider(Protocol):
    def create(self, spec: SandboxSpec, workdir: Path) -> SandboxSession: ...
    def destroy(self, session: SandboxSession) -> None: ...
