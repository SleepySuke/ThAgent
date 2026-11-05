"""requirement_agent MCP 接入：条件挂载（opt-in）+ policy 白名单 + prompt 教学。

默认路径零回归：无 AGENT_INFRA_MCP_CMD 时 tools 面与既有测试逐字节一致。
"""
import shlex

from agents.requirement_agent.agent import build_agent
from harness.contract import RunContext
from harness.policy import NODE_POLICIES
from harness.sandbox.manager import SandboxManager
from harness.sandbox.worktree import WorktreeProvider


def _agent():
    run = RunContext(trace_id="t", repo_path="x", commit="defect-1",
                     event_sink=lambda e, p: None)
    mgr = SandboxManager(WorktreeProvider(allowed_cmds=frozenset()), "runs")
    return build_agent(run, mgr, NODE_POLICIES["requirement_agent"])


def test_no_env_mounts_no_mcp(monkeypatch):
    """无 env：不挂 MCPToolset，tools 面与默认路径一致（零回归）。"""
    monkeypatch.delenv("AGENT_INFRA_MCP_CMD", raising=False)
    names = {t.__name__ for t in _agent().tools}
    assert names == {"read_diff", "read_file", "list_files"}


def test_env_mounts_mcp_toolset(monkeypatch):
    """有 env：给 LlmAgent 增挂 McpToolset（stdio，命令由 env 提供）。"""
    monkeypatch.setenv("AGENT_INFRA_MCP_CMD",
                       "python tests/mcp/fake_pr_server.py --verbose")
    agent = _agent()
    fns = {t.__name__ for t in agent.tools if hasattr(t, "__name__")}
    toolsets = [t for t in agent.tools if not hasattr(t, "__name__")]
    assert fns == {"read_diff", "read_file", "list_files"}  # 原工具不动
    assert len(toolsets) == 1
    conn = toolsets[0].connection_params
    assert shlex.split("python tests/mcp/fake_pr_server.py --verbose") == \
        [conn.command, *conn.args]
    assert toolsets[0].tool_filter == ["get_pr"]  # 只暴露白名单内的工具


def test_policy_whitelist_includes_mcp_tools():
    """坑 #16：T 层 MCP 工具名（裸名，ADK 默认无前缀）同步 G 层白名单。"""
    p = NODE_POLICIES["requirement_agent"]
    assert "get_pr" in p.allowed_tools
    assert {"read_diff", "read_file", "list_files"} <= p.allowed_tools


def test_prompt_teaches_pr_context_and_degradation():
    """prompt 教学：PR 号输入先 get_pr；工具不可用降级；凭证只走 env。"""
    text = _agent().instruction
    assert "get_pr" in text                       # 教学段点名工具
    assert "pr:" in text                          # PR 号输入形态（commit 形如 pr:N）
    assert "降级" in text                          # 工具不可用如实降级
    assert "凭证" in text and "env" in text        # redaction 注释：凭证只经 env


def test_policy_whitelist_covers_mcp_env_command(monkeypatch):
    """挂载命令可含参数（shlex 解析），白名单仍只含 get_pr——白名单与挂载解耦。"""
    monkeypatch.setenv("AGENT_INFRA_MCP_CMD", "npx -y @mcp/server-github")
    toolsets = [t for t in _agent().tools if not hasattr(t, "__name__")]
    assert [shlex.split("npx -y @mcp/server-github")] == \
        [[toolsets[0].connection_params.command, *toolsets[0].connection_params.args]]


def test_mcp_env_forwarding_for_credentials(monkeypatch, tmp_path):
    """t9-final I-2 回归：MCP_* 凭证 env 必须显式转发（SDK 白名单不含它们，
    env=None 时 token 到不了真实 server——401）；无 MCP_* env 时 env=None。"""
    monkeypatch.setenv("AGENT_INFRA_MCP_CMD", "python fake.py")
    monkeypatch.setenv("MCP_GITHUB_TOKEN", "ghp_test123")
    from agents.requirement_agent.agent import _build_mcp_toolset
    ts = _build_mcp_toolset()
    assert ts.connection_params.env == {"MCP_GITHUB_TOKEN": "ghp_test123"}
    monkeypatch.delenv("MCP_GITHUB_TOKEN")
    assert _build_mcp_toolset().connection_params.env is None
