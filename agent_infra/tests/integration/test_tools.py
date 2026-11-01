import inspect

from fixtures.build_demo_repo import build_demo_repo
from harness.contract import RunContext
from harness.sandbox.base import SandboxSpec
from harness.sandbox.manager import SandboxManager
from harness.sandbox.worktree import WorktreeProvider
from harness.tools import build_tools

ALLOWED = frozenset({"python", "pytest", "ls", "cat", "grep", "git"})
ALL_TOOLS = ["read_diff", "read_file", "write_file", "list_files", "run_cmd",
             "read_artifact"]


def make_tools(tmp_path, attempt=1, events=None):
    repo = build_demo_repo(tmp_path / "repo")
    mgr = SandboxManager(WorktreeProvider(allowed_cmds=ALLOWED), tmp_path / "runs")
    sink = (lambda e, p: events.append((e, p))) if events is not None \
        else (lambda e, p: None)
    run = RunContext(trace_id="t1", repo_path=str(repo), commit="defect-1",
                     attempt=attempt, event_sink=sink)
    return build_tools(run, mgr, ALL_TOOLS), mgr


async def test_tool_shapes_and_lazy_sandbox(tmp_path):
    tools, mgr = make_tools(tmp_path)
    by_name = {t.__name__: t for t in tools}
    assert set(by_name) == {"read_diff", "read_file", "write_file",
                            "list_files", "run_cmd", "read_artifact"}
    assert mgr.shutdown("t1") is None            # 未调用工具前无沙箱（惰性）
    d = await by_name["read_diff"]()
    assert "stats.py" in d["diff"]
    c = await by_name["read_file"]("shop/pricing.py")
    assert "DISCOUNT_TIERS" in c["content"]
    f = await by_name["list_files"]("shop/")
    assert "shop/pricing.py" in f["files"]
    w = await by_name["write_file"]("test_cases.py", "def test_x(): pass\n")
    assert w == {"ok": True, "path": "test_cases.py"}
    assert "def test_x" in (await by_name["read_file"]("test_cases.py"))["content"]
    r = await by_name["run_cmd"](["ls"])
    assert r["exit_code"] == 0
    assert mgr.shutdown("t1") is not None        # 用过即创建


async def test_errors_returned_not_raised(tmp_path):
    tools, mgr = make_tools(tmp_path)
    by_name = {t.__name__: t for t in tools}
    out = await by_name["read_file"]("../../etc/passwd")
    # 错误分型后顶层仍含 "error" 键（坑 #18 后向兼容），详情在 message
    assert "error" in out and "escape" in str(out["error"]).lower()
    mgr.shutdown("t1")


def test_tool_signatures_visible_to_llm(tmp_path):
    """ADK FunctionTool 靠签名声明参数：wraps 丢了签名 = LLM 拿到零参工具。"""
    tools, _ = make_tools(tmp_path)
    by_name = {t.__name__: t for t in tools}

    def required(name):
        return [p for p in inspect.signature(by_name[name]).parameters.values()
                if p.default is inspect.Parameter.empty
                and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)]

    assert "path" in inspect.signature(by_name["read_file"]).parameters
    assert "cmd" in inspect.signature(by_name["run_cmd"]).parameters
    assert "prefix" in inspect.signature(by_name["list_files"]).parameters
    assert {"path", "content"} <= set(inspect.signature(by_name["write_file"]).parameters)
    assert required("read_diff") == []


async def test_non_sandbox_errors_also_returned(tmp_path):
    """幻觉路径（FileNotFoundError 等）也必须转 error dict，不许炸到 agent。"""
    tools, mgr = make_tools(tmp_path)
    by_name = {t.__name__: t for t in tools}
    out = await by_name["read_file"]("no/such/file.py")
    # 错误分型：error 是结构化 dict，原文 message 非序列化 JSON 字符串
    assert "error" in out and isinstance(out["error"], dict) \
        and not out["error"]["message"].startswith("{")
    mgr.shutdown("t1")


async def test_read_artifact_from_artifacts_dir(tmp_path):
    """read_artifact 读 worktree 之外的 artifacts 目录，且只限该目录内。"""
    repo = build_demo_repo(tmp_path / "repo")
    mgr = SandboxManager(WorktreeProvider(allowed_cmds=ALLOWED), tmp_path / "runs")
    artifacts = tmp_path / "runs" / "t2" / "artifacts"
    artifacts.mkdir(parents=True)
    (artifacts / "cr_report.json").write_text('{"issues": []}', encoding="utf-8")
    run = RunContext(trace_id="t2", repo_path=str(repo), commit="defect-1",
                     artifacts_dir=str(artifacts))
    by_name = {t.__name__: t for t in build_tools(run, mgr, ["read_artifact"])}
    assert await by_name["read_artifact"]("cr_report.json") == \
        {"content": '{"issues": []}'}
    assert "error" in await by_name["read_artifact"]("../secret.txt")  # 越界拦截
    mgr.shutdown("t2")


async def test_attempt_gt_1_resets_sandbox_before_first_use(tmp_path):
    """矩阵 #16：attempt>1 首次工具调用先 reset 回 commit 干净态再复用会话。"""
    repo = build_demo_repo(tmp_path / "repo")
    mgr = SandboxManager(WorktreeProvider(allowed_cmds=ALLOWED), tmp_path / "runs")
    spec = SandboxSpec(repo_path=str(repo), commit="defect-1")
    dirty = mgr.get("t3", spec)                  # 上一轮 attempt 留下的脏沙箱
    dirty.write_file("junk.py", "dirty side effect\n")
    events: list = []
    run = RunContext(trace_id="t3", repo_path=str(repo), commit="defect-1",
                     attempt=2, event_sink=lambda e, p: events.append(e))
    by_name = {t.__name__: t for t in build_tools(run, mgr, ["read_file"])}
    out = await by_name["read_file"]("junk.py")
    assert "error" in out                        # reset 后副作用清零
    assert "sandbox_reset" in events
    mgr.shutdown("t3")


async def test_attempt_1_does_not_reset(tmp_path):
    """attempt==1（首轮）不 reset：正常惰性创建路径不受影响。"""
    events: list = []
    tools, mgr = make_tools(tmp_path, attempt=1, events=events)
    by_name = {t.__name__: t for t in tools}
    await by_name["write_file"]("keep.py", "kept\n")
    assert "sandbox_reset" not in events
    mgr.shutdown("t1")
