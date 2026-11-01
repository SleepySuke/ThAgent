import subprocess
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


def test_checkout_and_diff(session):
    d = session.diff()
    assert "stats.py" in d  # defect-1 相对父提交新增 stats.py


def test_read_file_and_list(session):
    assert "DISCOUNT_TIERS" in session.read_file("shop/pricing.py")
    assert "shop/pricing.py" in session.list_files("shop/")


def test_path_jail_blocks_escape(session):
    with pytest.raises(SandboxEscapeError):
        session.read_file("../repo/.git/config")
    with pytest.raises(SandboxEscapeError):
        session.read_file("/etc/passwd")


def test_cmd_whitelist_enforced(session):
    r = session.run(["curl", "http://example.com"])
    assert r.exit_code == 126 and "not allowed" in r.stderr


def test_cmd_timeout(tmp_path, session):
    provider = WorktreeProvider(allowed_cmds=ALLOWED)
    s2 = provider.create(
        SandboxSpec(repo_path=str(_repo_of(session)), commit="main",
                    limits=ResourceLimits(timeout_s=1, max_total_cmds=5)),
        workdir=session.worktree.parent.parent / "run2")
    try:
        r = s2.run(["python", "-c", "import time; time.sleep(5)"])
        assert r.timed_out and r.exit_code != 0
    finally:
        s2.destroy()


def test_cmd_count_limit(session):
    session.run(["ls"])
    session.run(["ls"])
    session.run(["ls"])
    with pytest.raises(SandboxLimitError):
        session.run(["ls"])


def test_snapshot_writes_artifacts(session, tmp_path):
    art = session.snapshot(tmp_path / "artifacts")
    assert (Path(art.path) / "commit.diff").exists()


def test_destroy_removes_worktree(session):
    wt = session.worktree
    session.destroy()
    assert not wt.exists()


def test_create_idempotent(tmp_path):
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
