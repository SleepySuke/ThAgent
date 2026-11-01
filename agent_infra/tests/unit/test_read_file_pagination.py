"""read_file 分页契约：offset/limit 续读拼接还原 + 超界空串（矩阵 #15）。"""
import subprocess

import pytest

from fixtures.build_demo_repo import build_demo_repo
from harness.contract import RunContext
from harness.sandbox.manager import SandboxManager
from harness.sandbox.worktree import WorktreeProvider
from harness.tools import build_tools

ALLOWED = frozenset({"ls"})


def _commit_big_file(repo, text) -> str:
    """大文件落一个新 commit，返回其 sha 作为沙箱 checkout 目标。"""
    (repo / "big.txt").write_text(text, encoding="utf-8")
    subprocess.run(["git", "-C", str(repo), "add", "."], check=True)
    # 同内容重复 commit 是 no-op——无变更时沿用当前 HEAD 即可
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "big file"],
                   capture_output=True, check=False)
    return subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"],
                          capture_output=True, text=True, check=True).stdout.strip()


@pytest.fixture()
def make_reader(tmp_path):
    """一个仓库 + 每次读取新 commit（worktree 独立 trace，互不复用）。"""
    repo = build_demo_repo(tmp_path / "repo")
    mgr = SandboxManager(WorktreeProvider(allowed_cmds=ALLOWED), tmp_path / "runs")
    counter = {"n": 0}

    async def reader(text: str, **kwargs) -> dict:
        counter["n"] += 1
        sha = _commit_big_file(repo, text)
        run = RunContext(trace_id=f"tp{counter['n']}", repo_path=str(repo),
                         commit=sha)
        tool = build_tools(run, mgr, ["read_file"])[0]
        return await tool("big.txt", **kwargs)

    yield reader
    mgr.shutdown("tp1")
    mgr.shutdown("tp2")
    mgr.shutdown("tp3")


async def test_large_file_truncated_by_default_limit(make_reader):
    out = await make_reader("a" * 30_000)
    assert out["total_len"] == 30_000
    assert out["truncated"] is True
    assert len(out["content"]) == 20_000


async def test_offset_pages_concatenate_to_full_content(make_reader):
    text = "".join(f"{i:04d}\n" for i in range(1000))  # 5000 字节
    p1 = await make_reader(text, offset=0, limit=2000)
    p2 = await make_reader(text, offset=2000, limit=2000)
    p3 = await make_reader(text, offset=4000, limit=2000)
    assert p1["content"] + p2["content"] + p3["content"] == text
    assert p1["truncated"] is True and p3["truncated"] is False


async def test_offset_beyond_total_returns_empty(make_reader):
    out = await make_reader("hello", offset=999_999)
    assert out == {"content": "", "truncated": False, "total_len": 5}
