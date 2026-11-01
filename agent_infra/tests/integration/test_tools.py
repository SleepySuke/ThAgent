import inspect

from fixtures.build_demo_repo import build_demo_repo
from harness.contract import RunContext
from harness.sandbox.manager import SandboxManager
from harness.sandbox.worktree import WorktreeProvider
from harness.tools import build_tools

ALLOWED = frozenset({"python", "pytest", "ls", "cat", "grep", "git"})
ALL_TOOLS = ["read_diff", "read_file", "write_file", "list_files", "run_cmd",
             "read_artifact"]


def make_tools(tmp_path):
    repo = build_demo_repo(tmp_path / "repo")
    mgr = SandboxManager(WorktreeProvider(allowed_cmds=ALLOWED), tmp_path / "runs")
    run = RunContext(trace_id="t1", repo_path=str(repo), commit="defect-1")
    return build_tools(run, mgr, ALL_TOOLS), mgr


def test_tool_shapes_and_lazy_sandbox(tmp_path):
    tools, mgr = make_tools(tmp_path)
    by_name = {t.__name__: t for t in tools}
    assert set(by_name) == {"read_diff", "read_file", "write_file",
                            "list_files", "run_cmd", "read_artifact"}
    assert mgr.shutdown("t1") is None            # 未调用工具前无沙箱（惰性）
    d = by_name["read_diff"]()
    assert "stats.py" in d["diff"]
    c = by_name["read_file"]("shop/pricing.py")
    assert "DISCOUNT_TIERS" in c["content"]
    f = by_name["list_files"]("shop/")
    assert "shop/pricing.py" in f["files"]
    w = by_name["write_file"]("test_cases.py", "def test_x(): pass\n")
    assert w == {"ok": True, "path": "test_cases.py"}
    assert "def test_x" in by_name["read_file"]("test_cases.py")["content"]
    r = by_name["run_cmd"](["ls"])
    assert r["exit_code"] == 0
    assert mgr.shutdown("t1") is not None        # 用过即创建


def test_errors_returned_not_raised(tmp_path):
    tools, mgr = make_tools(tmp_path)
    by_name = {t.__name__: t for t in tools}
    out = by_name["read_file"]("../../etc/passwd")
    assert "error" in out and "escape" in out["error"].lower()
    mgr.shutdown("t1")


def test_tool_signatures_visible_to_llm(tmp_path):
    """ADK FunctionTool 靠签名声明参数：wraps 丢了签名 = LLM 拿到零参工具。"""
    tools, _ = make_tools(tmp_path)

    def required(name):
        return [p for p in inspect.signature(by_name[name]).parameters.values()
                if p.default is inspect.Parameter.empty
                and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)]

    by_name = {t.__name__: t for t in tools}
    assert "path" in inspect.signature(by_name["read_file"]).parameters
    assert "cmd" in inspect.signature(by_name["run_cmd"]).parameters
    assert "prefix" in inspect.signature(by_name["list_files"]).parameters
    assert {"path", "content"} <= set(inspect.signature(by_name["write_file"]).parameters)
    assert required("read_diff") == []


def test_non_sandbox_errors_also_returned(tmp_path):
    """幻觉路径（FileNotFoundError 等）也必须转 error dict，不许炸到 agent。"""
    tools, mgr = make_tools(tmp_path)
    by_name = {t.__name__: t for t in tools}
    out = by_name["read_file"]("no/such/file.py")
    assert "error" in out and not out["error"].startswith("{")
    mgr.shutdown("t1")


def test_read_artifact_from_artifacts_dir(tmp_path):
    """read_artifact 读 worktree 之外的 artifacts 目录，且只限该目录内。"""
    repo = build_demo_repo(tmp_path / "repo")
    mgr = SandboxManager(WorktreeProvider(allowed_cmds=ALLOWED), tmp_path / "runs")
    artifacts = tmp_path / "runs" / "t2" / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "cr_report.json").write_text('{"issues": []}', encoding="utf-8")
    run = RunContext(trace_id="t2", repo_path=str(repo), commit="defect-1",
                     artifacts_dir=str(artifacts))
    by_name = {t.__name__: t for t in build_tools(run, mgr, ["read_artifact"])}
    assert by_name["read_artifact"]("cr_report.json") == {"content": '{"issues": []}'}
    assert "error" in by_name["read_artifact"]("../secret.txt")  # 越界拦截
    mgr.shutdown("t2")
