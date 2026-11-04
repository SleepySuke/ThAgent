"""Fake MCP stdio server（纯 stdlib，零依赖）：提供一个 `get_pr` 工具。

协议：stdin/stdout 逐行 JSON-RPC 2.0（MCP stdio transport）。实现 MCP 生命
周期的最小子集：initialize / notifications/initialized / tools/list /
tools/call。stderr 留给日志（stdio transport 下 stdout 是协议通道，不能混写）。

用法：`uv run python tests/mcp/fake_pr_server.py`——由 McpToolset（stdio
transport）作为子进程拉起，测试与 e2e 均不依赖 mcp 服务端 SDK。
"""
from __future__ import annotations

import json
import sys

# canned 数据：pr_number=1/2 两套（integration 测试断言两套互异）
_PRS = {
    1: {
        "title": "Fix discount stack overflow in pricing",
        "body": "promo 与 tier discount 叠加导致总价越界",
        "files": ["shop/pricing.py", "tests/test_pricing.py"],
    },
    2: {
        "title": "Add export endpoint for reports",
        "body": "新增 CSV 导出接口",
        "files": ["api/export.py"],
    },
}

PROTOCOL_VERSION = "2024-11-05"


def _handle(req: dict) -> dict | None:  # noqa: PLR0911 -- 协议分派，平铺最可读
    method = req.get("method", "")
    rid = req.get("id")
    if method == "initialize":
        # 回显客户端请求版本（在支持集内）——比固定值稳：mcp SDK 升版不再
        # 依赖旧版本号被接受（t7-rev Minor）
        asked = req.get("params", {}).get("protocolVersion", PROTOCOL_VERSION)
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {
                "protocolVersion": asked,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fake-pr-server", "version": "0.1.0"},
            },
        }
    if method.startswith("notifications/"):  # initialized 等：无 id，不回包
        return None
    if method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {
                "tools": [{
                    "name": "get_pr",
                    "description": "获取 PR 标题/描述/变更文件",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "pr_number": {"type": "integer",
                                          "description": "PR 编号"},
                        },
                        "required": ["pr_number"],
                    },
                }],
            },
        }
    if method == "tools/call":
        pr_number = int(req["params"]["arguments"]["pr_number"])
        pr = _PRS.get(pr_number)
        if pr is None:
            return {
                "jsonrpc": "2.0",
                "id": rid,
                "result": {
                    "content": [{"type": "text",
                                 "text": f"unknown pr_number={pr_number}"}],
                    "isError": True,
                },
            }
        return {
            "jsonrpc": "2.0",
            "id": rid,
            "result": {
                "content": [{"type": "text", "text": json.dumps(pr)}],
                "isError": False,
            },
        }
    # 未知方法：协议要求回 error（有 id 时）
    if rid is not None:
        return {"jsonrpc": "2.0", "id": rid,
                "error": {"code": -32601, "message": f"no such method {method}"}}
    return None


def main() -> None:
    print("fake_pr_server ready", file=sys.stderr)  # stderr = 日志通道
    for raw_line in sys.stdin:
        line = raw_line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            resp = _handle(req)
        except Exception as exc:  # 单条坏行不打断 server
            print(f"bad request: {exc}", file=sys.stderr)
            continue
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
