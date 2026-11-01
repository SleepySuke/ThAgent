"""Git Worktree 沙箱实现。

# ponytail: 进程级限制是 macOS 天花板（无 cgroup）；换 docker/gVisor 后由容器
runtime 提供 CPU/内存硬限制，SandboxSession 接口不变。
"""
from __future__ import annotations

import asyncio
import contextlib
import os
import subprocess
from pathlib import Path

from harness.sandbox.base import (
    Artifact,
    CmdResult,
    ResourceLimits,
    SandboxEscapeError,
    SandboxLimitError,
    SandboxSpec,
)


class WorktreeSession:
    def __init__(self, worktree: Path, repo_path: str, commit: str,
                 allowed_cmds: frozenset[str], limits: ResourceLimits) -> None:
        self.worktree = worktree
        self._repo = repo_path
        self._commit = commit
        self._allowed = allowed_cmds
        self._limits = limits
        self._cmd_count = 0

    # ---- 内部 ----
    def _git(self, *args: str, cwd: Path | None = None) -> str:
        r = subprocess.run(["git", *args], cwd=cwd or self.worktree,
                           capture_output=True, text=True, check=False)
        if r.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)}: {r.stderr}")
        return r.stdout

    def _jail(self, rel: str) -> Path:
        root = self.worktree.resolve()
        p = (root / rel).resolve()
        if root != p and root not in p.parents:
            raise SandboxEscapeError(f"path escapes sandbox: {rel}")
        return p

    # ---- SandboxSession 协议 ----
    async def run(self, cmd: list[str]) -> CmdResult:
        # ponytail: exact-N 契约——max_total_cmds=N 允许恰好 N 条，第 N+1 条抛错
        if self._cmd_count >= self._limits.max_total_cmds:
            raise SandboxLimitError(
                f"max_total_cmds reached: {self._limits.max_total_cmds}")
        head = os.path.basename(cmd[0]) if cmd else ""
        if head not in self._allowed:
            return CmdResult(cmd=cmd, exit_code=126, stdout="",
                             stderr=f"command not allowed: {head}")
        self._cmd_count += 1
        proc = await asyncio.create_subprocess_exec(
            *cmd, cwd=self.worktree,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        try:
            out_b, err_b = await asyncio.wait_for(
                proc.communicate(), self._limits.timeout_s)
            out, err, rc, truncated = (
                out_b.decode(errors="replace"), err_b.decode(errors="replace"),
                proc.returncode, False)
        except TimeoutError:
            # 矩阵 #14：wait_for 只取消 communicate，不杀子进程——显式 kill
            #（竞态容错：超时瞬间子进程恰好自行退出时 kill 抛 LookupError，
            # 吞掉保 124 形态不丢）
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            out_b, _ = await proc.communicate()  # 收尸防僵尸，取残余 stdout
            out = out_b.decode(errors="replace")
            err = "sandbox: command timed out"
            rc, truncated = 124, True
        except asyncio.CancelledError:
            # 调用方 cancel（engine pause/shutdown）同样不留孤儿；kill 抛错
            # 不得顶掉 CancelledError（取消语义优先），收尸后 bare raise
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            await proc.wait()
            raise
        limit = self._limits.max_output_bytes
        return CmdResult(
            cmd=cmd, exit_code=rc,
            stdout=out[:limit], stderr=err[:limit],
            truncated=truncated or len(out) > limit or len(err) > limit,
            timed_out=rc == 124)

    def read_file(self, path: str) -> str:
        return self._jail(path).read_text(encoding="utf-8", errors="replace")

    def write_file(self, path: str, content: str) -> None:
        p = self._jail(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def list_files(self, prefix: str = "") -> list[str]:
        root = self.worktree.resolve()
        base = self._jail(prefix or ".")
        files = [str(p.relative_to(root)) for p in sorted(base.rglob("*"))
                 if p.is_file() and ".git" not in p.parts]
        return files[:500]

    def diff(self) -> str:
        return self._git("diff", "HEAD~1", "HEAD")

    def reset_to_commit(self) -> None:
        """回 commit 干净态（attempt>1 reset，幂等）：跟踪文件 checkout 覆写
        + 未跟踪文件 clean。副作用清零 = 沙箱天然回滚。"""
        self._git("checkout", self._commit, "--", ".")
        self._git("clean", "-fd")

    def snapshot(self, artifacts_dir: Path) -> Artifact:
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        (artifacts_dir / "commit.diff").write_text(self.diff(), encoding="utf-8")
        (artifacts_dir / "worktree.status").write_text(
            self._git("status", "--porcelain"), encoding="utf-8")
        return Artifact(path=str(artifacts_dir))

    def destroy(self) -> None:
        subprocess.run(["git", "-C", self._repo, "worktree", "remove",
                        "--force", str(self.worktree)],
                       capture_output=True, text=True, check=False)  # 尽力回收


class WorktreeProvider:
    def __init__(self, allowed_cmds: frozenset[str]) -> None:
        self._allowed = allowed_cmds

    def create(self, spec: SandboxSpec, workdir: Path) -> WorktreeSession:
        workdir.mkdir(parents=True, exist_ok=True)
        wt = workdir / "sandbox"
        # 幂等：同一 run 内多 agent 共享 worktree（runs/<rid>/sandbox），已存在
        # 则复用不再 git worktree add（否则报 already registered）
        if not (wt / ".git").exists():
            # ponytail: 先 prune——run 目录被外部 rmtree（冒烟脚本/手清）会留下
            # 指向已删路径的孤儿元数据，积累后 worktree add 失败（全链冒烟实测
            # 踩中）。prune 幂等且只清死条目，活动 worktree 不受影响
            subprocess.run(["git", "-C", spec.repo_path, "worktree", "prune"],
                           capture_output=True, check=False)
            r = subprocess.run(
                ["git", "-C", spec.repo_path, "worktree", "add", "--detach",
                 str(wt), spec.commit],
                capture_output=True, text=True, check=False)
            if r.returncode != 0:
                raise RuntimeError(f"worktree add failed: {r.stderr}")
        return WorktreeSession(wt, spec.repo_path, spec.commit,
                               self._allowed, spec.limits)

    def destroy(self, session: WorktreeSession) -> None:
        session.destroy()
