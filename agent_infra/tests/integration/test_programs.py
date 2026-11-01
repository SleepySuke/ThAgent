import pytest

from fixtures.build_demo_repo import build_demo_repo
from harness.programs.case_executor import execute_cases
from harness.sandbox.base import SandboxSpec
from harness.sandbox.worktree import WorktreeProvider

ALLOWED = frozenset({"python", "pytest"})


def _worktree(tmp_path, run_id):
    repo = build_demo_repo(tmp_path / "repo")
    provider = WorktreeProvider(allowed_cmds=ALLOWED)
    return provider.create(SandboxSpec(repo_path=str(repo), commit="main"),
                           workdir=tmp_path / "runs" / run_id)


def test_execute_cases_runs_generated_script(tmp_path):
    session = _worktree(tmp_path, "r1")
    try:
        (session.worktree / "test_cases.py").write_text(
            "def test_ok():\n    assert 1 == 1\n", encoding="utf-8")
        result = execute_cases(tmp_path / "runs", "r1", [])
        assert result["exit_code"] == 0
        assert "passed" in result["stdout"]
    finally:
        session.destroy()


def test_execute_cases_collects_failure_exit_code(tmp_path):
    session = _worktree(tmp_path, "r2")
    try:
        (session.worktree / "test_cases.py").write_text(
            "def test_fail():\n    assert False\n", encoding="utf-8")
        result = execute_cases(tmp_path / "runs", "r2", [])
        assert result["exit_code"] != 0
        assert "failed" in result["stdout"]
    finally:
        session.destroy()


def test_execute_cases_missing_script_raises(tmp_path):
    session = _worktree(tmp_path, "r3")
    try:
        with pytest.raises(ValueError, match="not found"):
            execute_cases(tmp_path / "runs", "r3", [])
    finally:
        session.destroy()
