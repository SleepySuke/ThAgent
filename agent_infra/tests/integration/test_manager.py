from pathlib import Path

from fixtures.build_demo_repo import build_demo_repo
from harness.sandbox.base import SandboxSpec
from harness.sandbox.manager import SandboxManager
from harness.sandbox.worktree import WorktreeProvider

ALLOWED = frozenset({"ls"})


def test_lazy_create_and_reuse(tmp_path):
    repo = build_demo_repo(tmp_path / "repo")
    mgr = SandboxManager(WorktreeProvider(allowed_cmds=ALLOWED), tmp_path / "runs")
    spec = SandboxSpec(repo_path=str(repo), commit="main")
    assert mgr.shutdown("r1") is None          # 未创建过：惰性，无副作用
    s1 = mgr.get("r1", spec)
    s2 = mgr.get("r1", spec)
    assert s1 is s2                             # 会话内复用
    art = mgr.shutdown("r1")
    assert art is not None
    assert (Path(art.path) / "commit.diff").exists()
    assert not s1.worktree.exists()             # 已销毁
    assert mgr.shutdown("r1") is None           # 幂等


def test_two_runs_isolated(tmp_path):
    repo = build_demo_repo(tmp_path / "repo")
    mgr = SandboxManager(WorktreeProvider(allowed_cmds=ALLOWED), tmp_path / "runs")
    spec = SandboxSpec(repo_path=str(repo), commit="main")
    a = mgr.get("ra", spec)
    b = mgr.get("rb", spec)
    assert a.worktree != b.worktree            # 多 run 并存 = 多 agent workspace 隔离
    mgr.shutdown("ra")
    assert b.worktree.exists()                  # 不误伤
    mgr.shutdown("rb")
