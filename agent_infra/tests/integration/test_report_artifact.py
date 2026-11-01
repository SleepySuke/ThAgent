"""集成：report 的 markdown 产物落盘——executor 按 artifact_name 后缀分流。"""
import json
from dataclasses import replace

from fastapi.testclient import TestClient

from agent_server import build_a2a_app, load_agent_by_name
from harness.sandbox.manager import SandboxManager
from harness.sandbox.worktree import WorktreeProvider

REPORT = {"summary": "整体可控",
          "verdicts": [{"node": "cr_agent", "verdict": "request_changes"}],
          "stats": {"issues": 1},
          "markdown": "# 审查报告\n上游结论：requirement_agent 的验收 + "
                      "case_executor 的执行结果。"}


def _app(tmp_path):
    mgr = SandboxManager(
        WorktreeProvider(allowed_cmds=frozenset()), tmp_path / "runs")

    async def report_run(run, prompt):
        return json.dumps(REPORT)

    spec = replace(load_agent_by_name("report_agent"),
                   url="http://127.0.0.1:8109")
    return build_a2a_app(tmp_path / "runs", mgr, spec, run_agent=report_run)


def test_report_markdown_artifact_written(tmp_path):
    agent_input = {"run_id": "t-md", "node_id": "report_agent",
                   "input_data": {"repo": "x", "commit": "d"},
                   "context_id": "t-md", "history": []}
    with TestClient(_app(tmp_path)) as c:
        r = c.post("/a2a/jsonrpc", headers={"A2A-Version": "1.0"}, json={
            "jsonrpc": "2.0", "id": "1", "method": "SendMessage",
            "params": {"message": {
                "role": "ROLE_USER",
                "parts": [{"text": json.dumps(agent_input)}],
                "messageId": "m1", "contextId": "t-md"}}})
        assert r.status_code == 200 and "error" not in r.json(), r.text
    md = tmp_path / "runs" / "t-md" / "artifacts" / "execution_report.md"
    assert md.read_text(encoding="utf-8") == REPORT["markdown"]  # 原文落盘
    # 既有 .json 落盘路径不受影响（cr_report.json 契约由既有测试守护）
    assert not (tmp_path / "runs" / "t-md" / "artifacts"
                / "execution_report.md.json").exists()
