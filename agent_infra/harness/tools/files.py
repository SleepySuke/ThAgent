"""文件类沙箱工具：read_file / write_file / list_files。

每个工具是 `build(run, session)` 工厂——session 是惰性会话（见 _base）。
内层函数名即工具名（ADK FunctionTool 靠 __name__ 标识工具，不能统一叫 f）。
"""
from __future__ import annotations

from harness.tools._base import _SPECS, _wrap


def read_file(run, session):
    @_wrap(_SPECS["read_file"])
    async def read_file(path: str, offset: int = 0, limit: int = 20_000) -> dict:
        """读取沙箱内指定文件内容。path 为相对沙箱根的路径。

        Args:
            path: 相对沙箱根的文件路径。
            offset: 起始字符偏移（分页续读），默认 0。
            limit: 本次最多返回的字符数，默认 20000。
        """
        content = session().read_file(path)
        offset, limit = max(0, offset), max(0, limit)   # LLM 误传负数的边界守卫
        chunk = content[offset:offset + limit]
        return {"content": chunk,
                "truncated": offset + limit < len(content),
                "total_len": len(content)}
    return read_file


def write_file(run, session):
    @_wrap(_SPECS["write_file"])
    async def write_file(path: str, content: str) -> dict:
        """在沙箱内写文件（相对路径），用于生成测试脚本等产物。"""
        session().write_file(path, content)
        return {"ok": True, "path": path}
    return write_file


def list_files(run, session):
    @_wrap(_SPECS["list_files"])
    async def list_files(prefix: str = "") -> dict:
        """列出沙箱内匹配前缀的文件列表。"""
        return {"files": session().list_files(prefix)}
    return list_files
