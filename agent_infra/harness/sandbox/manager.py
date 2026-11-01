"""沙箱生命周期管理：惰性创建 + 会话复用 + 统一回收。

生命周期归 harness（决策），不归 LLM。多 agent/k8s 后换带 TTL 驱逐的池。
# ponytail: 单进程内存缓存；升级路径见 docs/sandbox-comparison.md
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path

from harness.checkpoint import load_checkpoint
from harness.sandbox.base import Artifact, SandboxProvider, SandboxSession, SandboxSpec

# boot sweep 视为终态的 checkpoint harness_state（executing/paused/review_pending
# 是活 run，跳过——矩阵 #13）。活 run 的 checkpoint 先于任何沙箱创建落盘
# （engine 建目录即写 executing 态），故「刚起 run 被误杀」仅在 checkpoint
# 损坏（视同缺失→回收）时发生——接受该面：损坏即无进度可续，沙箱可再生
_TERMINAL_STATES = {"completed", "failed", "cancelled", "interrupted"}


class SandboxManager:
    def __init__(self, provider: SandboxProvider, runs_root: Path) -> None:
        self._provider = provider
        self._runs_root = Path(runs_root)
        self._sessions: dict[str, SandboxSession] = {}
        self._last_active: dict[str, float] = {}  # run_id → monotonic 活跃时刻

    def get(self, run_id: str, spec: SandboxSpec) -> SandboxSession:
        self.touch(run_id)
        if run_id not in self._sessions:
            self._sessions[run_id] = self._provider.create(
                spec, self._runs_root / run_id)
        return self._sessions[run_id]

    def touch(self, run_id: str) -> None:
        """活跃心跳：工具调用路径刷新 TTL（矩阵 #12：活跃永不达阈值）。"""
        self._last_active[run_id] = time.monotonic()

    def sweep(self, ttl_s: float) -> list[str]:
        """TTL 兜底（防线层2）：idle > ttl 的 session snapshot+destroy+pop。

        覆盖 engine 崩溃 / shutdown HTTP 失败的孤儿。粒度红线：只回收
        session 与 worktree（可再生），run 目录不动。"""
        now = time.monotonic()
        stale = [rid for rid, ts in self._last_active.items()
                 if rid in self._sessions and now - ts > ttl_s]
        for rid in stale:
            self.shutdown(rid)
            self._last_active.pop(rid, None)
        return stale

    def boot_sweep(self) -> list[str]:
        """启动自愈（防线层3）：runs/*/sandbox 中 checkpoint 终态/缺失的残留
        回收 + `git worktree prune`。与 checkpoint trace 自愈同构：幂等，
        append-only 事实源做裁判。"""
        root = self._runs_root
        if not root.exists():
            return []
        reclaimed: list[str] = []
        for run_dir in sorted(root.iterdir()):
            wt = run_dir / "sandbox"
            if not run_dir.is_dir() or not (wt / ".git").exists():
                continue
            try:
                cp = load_checkpoint(root, run_dir.name)
            except json.JSONDecodeError:  # 损坏视同缺失：无主目录回收
                cp = None
            if cp and cp.get("harness_state") not in _TERMINAL_STATES:
                continue  # executing/paused 等活 run 跳过
            self._destroy_orphan(wt)
            reclaimed.append(run_dir.name)
        return reclaimed

    @staticmethod
    def _destroy_orphan(wt: Path) -> None:
        """无 session 对象的孤儿回收：从 sandbox/.git 的 gitdir 指回反解主仓库。"""
        repo: Path | None = None
        try:
            text = (wt / ".git").read_text(encoding="utf-8").strip()
            gitdir = Path(text.removeprefix("gitdir: ").strip())
            # <repo>/.git/worktrees/<name> → <repo>
            repo = gitdir.parent.parent.parent
            subprocess.run(
                ["git", "-C", str(repo), "worktree", "remove", "--force",
                 str(wt)], capture_output=True, text=True, check=False)
        except OSError:  # .git 指回文件缺失：目录已残破，只剩 prune
            pass
        finally:
            if repo is not None:
                # remove 失败（目录已被手清）也要 prune 死元数据；prune 只清死条目
                subprocess.run(["git", "-C", str(repo), "worktree", "prune"],
                               capture_output=True, check=False)

    def reset(self, run_id: str, spec: SandboxSpec) -> None:
        """attempt>1 沙箱回 commit 干净态（副作用清零，沙箱=天然回滚）。"""
        self.get(run_id, spec).reset_to_commit()

    def shutdown(self, run_id: str) -> Artifact | None:
        session = self._sessions.pop(run_id, None)
        if session is None:
            return None
        self._last_active.pop(run_id, None)
        artifact = None
        try:
            artifact = session.snapshot(self._runs_root / run_id / "artifacts")
        finally:
            session.destroy()  # snapshot 失败不阻塞销毁
        return artifact
