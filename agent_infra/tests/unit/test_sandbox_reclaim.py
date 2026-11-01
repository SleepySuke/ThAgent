"""沙箱回收防线：TTL 清扫（层2）+ boot sweep（层3）。

粒度红线：只回收 session 与 worktree（可再生）；run 目录（checkpoint/trace/
artifacts）是审计资产，不得混扫。
"""

import subprocess
from pathlib import Path

from fixtures.build_demo_repo import build_demo_repo
from harness.checkpoint import save_checkpoint
from harness.sandbox.base import SandboxSpec
from harness.sandbox.manager import SandboxManager
from harness.sandbox.worktree import WorktreeProvider

ALLOWED = frozenset({"ls"})


def _mgr(tmp_path) -> tuple[SandboxManager, SandboxSpec, Path]:
    repo = build_demo_repo(tmp_path / "repo")
    mgr = SandboxManager(WorktreeProvider(allowed_cmds=ALLOWED),
                         tmp_path / "runs")
    return mgr, SandboxSpec(repo_path=str(repo), commit="main"), repo


def _cp(runs: Path, rid: str, state: str) -> None:
    save_checkpoint(runs, rid, {"run_id": rid, "context_id": rid,
                                "current_node": None, "harness_state": state,
                                "completed_nodes": [], "node_outputs": {}})


async def test_sweep_reclaims_idle_and_keeps_active(tmp_path):
    """矩阵 #12：idle 超时回收（snapshot 先行）；touch 后活跃永不达 TTL。"""
    mgr, spec, _repo = _mgr(tmp_path)
    runs = tmp_path / "runs"
    s = mgr.get("r1", spec)
    s.write_file("notes.txt", "dirty")
    assert mgr.sweep(ttl_s=999) == []            # 刚 get（touch）→ 活跃
    mgr._last_active["r1"] -= 10_000             # 人为老化超时
    mgr.touch("r1")                              # 活跃心跳刷新 → 不回收
    assert mgr.sweep(ttl_s=60) == []
    assert s.worktree.exists()
    mgr._last_active["r1"] -= 10_000             # 再次老化 → 本次回收
    assert mgr.sweep(ttl_s=60) == ["r1"]
    assert not s.worktree.exists()               # destroy 生效
    assert (runs / "r1" / "artifacts" / "worktree.status").exists()  # snapshot 落盘
    assert (runs / "r1").is_dir()               # run 目录不混扫（粒度红线）
    assert mgr.sweep(ttl_s=60) == []             # 幂等，不重复回收


async def test_boot_sweep_reclaims_terminal_and_skips_executing(tmp_path):
    """矩阵 #13：checkpoint 终态/缺失/损坏 → 回收；executing/paused 等非终态跳过。"""
    mgr, spec, _repo = _mgr(tmp_path)
    runs = tmp_path / "runs"
    _cp(runs, "r-done", "completed")
    _cp(runs, "r-run", "executing")
    _cp(runs, "r-paused", "paused")
    # r-none：无 checkpoint（engine 崩溃残留）；r-corrupt：损坏（视同缺失→回收）
    for rid in ("r-done", "r-run", "r-paused", "r-none", "r-corrupt"):
        mgr.get(rid, spec)
    (runs / "r-corrupt" / "checkpoint.json").write_text("{torn", encoding="utf-8")
    fresh = SandboxManager(WorktreeProvider(allowed_cmds=ALLOWED), runs)
    assert sorted(fresh.boot_sweep()) == ["r-corrupt", "r-done", "r-none"]
    assert not (runs / "r-done" / "sandbox").exists()
    assert not (runs / "r-none" / "sandbox").exists()
    assert not (runs / "r-corrupt" / "sandbox").exists()
    assert (runs / "r-run" / "sandbox").exists()           # 非终态跳过
    # 挂起中不回收（Task 4 后同款保护 review_pending）
    assert (runs / "r-paused" / "sandbox").exists()
    assert (runs / "r-done" / "checkpoint.json").exists()  # run 目录不混扫


async def test_boot_sweep_prunes_git_metadata(tmp_path):
    """回收后 .git/worktrees 无死条目（prune 清元数据，remove 清目录）。"""
    mgr, spec, repo = _mgr(tmp_path)
    s = mgr.get("r1", spec)
    wt = s.worktree
    fresh = SandboxManager(WorktreeProvider(allowed_cmds=ALLOWED),
                           tmp_path / "runs")
    fresh.boot_sweep()
    assert not wt.exists()
    out = subprocess.run(["git", "-C", str(repo), "worktree", "list"],
                         capture_output=True, text=True, check=True).stdout
    assert str(wt) not in out
