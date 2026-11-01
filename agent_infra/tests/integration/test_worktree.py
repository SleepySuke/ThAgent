import asyncio
import subprocess
import time
from pathlib import Path

import pytest

from fixtures.build_demo_repo import build_demo_repo
from harness.sandbox.base import (
    ResourceLimits,
    SandboxEscapeError,
    SandboxLimitError,
    SandboxSpec,
)
from harness.sandbox.worktree import WorktreeProvider

ALLOWED = frozenset({"python", "pytest", "ruff", "ls", "cat", "grep", "git"})


def _repo_of(session) -> Path:
    """worktree 的 git file 指回主仓库。"""
    out = subprocess.run(
        ["git", "-C", str(session.worktree), "rev-parse", "--path-format=absolute",
         "--git-common-dir"], capture_output=True, text=True, check=True).stdout.strip()
    return Path(out).parent


def _sleep_proc_alive() -> bool:
    """孤儿检查：sleep 30 的子进程是否还活着（kill 生效即无孤儿）。"""
    out = subprocess.run(["pgrep", "-f", "time.sleep(30)"],
                         capture_output=True, text=True, check=False)
    return out.returncode == 0


@pytest.fixture()
def session(tmp_path):
    repo = build_demo_repo(tmp_path / "repo")
    provider = WorktreeProvider(allowed_cmds=ALLOWED)
    s = provider.create(
        SandboxSpec(repo_path=str(repo), commit="defect-1",
                    limits=ResourceLimits(timeout_s=10, max_total_cmds=3)),
        workdir=tmp_path / "run")
    yield s
    s.destroy()


async def test_checkout_and_diff(session):
    d = session.diff()
    assert "stats.py" in d  # defect-1 相对父提交新增 stats.py


async def test_read_file_and_list(session):
    assert "DISCOUNT_TIERS" in session.read_file("shop/pricing.py")
    assert "shop/pricing.py" in session.list_files("shop/")


async def test_path_jail_blocks_escape(session):
    with pytest.raises(SandboxEscapeError):
        session.read_file("../repo/.git/config")
    with pytest.raises(SandboxEscapeError):
        session.read_file("/etc/passwd")


async def test_cmd_whitelist_enforced(session):
    r = await session.run(["curl", "http://example.com"])
    assert r.exit_code == 126 and "not allowed" in r.stderr


async def test_cmd_timeout(tmp_path, session):
    provider = WorktreeProvider(allowed_cmds=ALLOWED)
    s2 = provider.create(
        SandboxSpec(repo_path=str(_repo_of(session)), commit="main",
                    limits=ResourceLimits(timeout_s=1, max_total_cmds=5)),
        workdir=session.worktree.parent.parent / "run2")
    try:
        r = await s2.run(["python", "-c", "import time; time.sleep(5)"])
        assert r.timed_out and r.exit_code != 0
    finally:
        s2.destroy()


async def test_timeout_kills_child_process(tmp_path, session):
    """矩阵 #14：超时不仅要快速返回 124，还要杀掉子进程不留孤儿。"""
    provider = WorktreeProvider(allowed_cmds=ALLOWED)
    s2 = provider.create(
        SandboxSpec(repo_path=str(_repo_of(session)), commit="main",
                    limits=ResourceLimits(timeout_s=1, max_total_cmds=5)),
        workdir=session.worktree.parent.parent / "run3")
    try:
        start = time.monotonic()
        r = await s2.run(["python", "-c", "import time; time.sleep(30)"])
        elapsed = time.monotonic() - start
        assert r.exit_code == 124 and r.timed_out and r.truncated
        assert elapsed < 10                      # 快速返回，没干等 30s
        await asyncio.sleep(0.3)                 # 给 kill 一点传播时间
        assert not _sleep_proc_alive()
    finally:
        s2.destroy()


async def test_cancel_kills_child_process(session):
    """矩阵 #14：调用方 cancel（engine pause/shutdown）同样杀子进程不留孤儿。"""
    task = asyncio.create_task(
        session.run(["python", "-c", "import time; time.sleep(30)"]))
    await asyncio.sleep(0.5)                     # 子进程已起
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(0.3)
    assert not _sleep_proc_alive()


async def test_cmd_count_limit(session):
    await session.run(["ls"])
    await session.run(["ls"])
    await session.run(["ls"])
    with pytest.raises(SandboxLimitError):
        await session.run(["ls"])


async def test_snapshot_writes_artifacts(session, tmp_path):
    art = session.snapshot(tmp_path / "artifacts")
    assert (Path(art.path) / "commit.diff").exists()


async def test_destroy_removes_worktree(session):
    wt = session.worktree
    session.destroy()
    assert not wt.exists()


async def test_reset_to_commit_restores_clean_state(session):
    """attempt>1 reset：未跟踪文件消失、被改的跟踪文件恢复到 commit 版本。"""
    session.write_file("untracked_junk.py", "junk\n")
    session.write_file("shop/pricing.py", "# overwritten\n")
    session.reset_to_commit()
    with pytest.raises(FileNotFoundError):
        session.read_file("untracked_junk.py")
    assert "DISCOUNT_TIERS" in session.read_file("shop/pricing.py")


async def test_create_idempotent(tmp_path):
    repo = build_demo_repo(tmp_path / "repo")
    provider = WorktreeProvider(allowed_cmds=ALLOWED)
    spec = SandboxSpec(repo_path=str(repo), commit="main")
    s1 = provider.create(spec, workdir=tmp_path / "run")
    try:
        s2 = provider.create(spec, workdir=tmp_path / "run")  # 复用，不重复 add
        assert s1.worktree == s2.worktree
        out = subprocess.run(["git", "-C", str(repo), "worktree", "list"],
                             capture_output=True, text=True, check=True).stdout
        assert out.count(str(s1.worktree)) == 1  # 只注册一次
    finally:
        s1.destroy()
