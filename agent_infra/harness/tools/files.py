"""文件类沙箱工具：read_file / write_file / list_files。

每个工具是 `build(run, session)` 工厂——session 是惰性会话（见 _base）。
内层函数名即工具名（ADK FunctionTool 靠 __name__ 标识工具，不能统一叫 f）。
"""
from __future__ import annotations

from harness.tools._base import _guard


def read_file(run, session):
    @_guard
    def read_file(path: str) -> dict:
        """读取沙箱内指定文件内容。path 为相对沙箱根的路径。"""
        return {"content": session().read_file(path)}
    return read_file


def write_file(run, session):
    @_guard
    def write_file(path: str, content: str) -> dict:
        """在沙箱内写文件（相对路径），用于生成测试脚本等产物。"""
        session().write_file(path, content)
        return {"ok": True, "path": path}
    return write_file


def list_files(run, session):
    @_guard
    def list_files(prefix: str = "") -> dict:
        """列出沙箱内匹配前缀的文件列表。"""
        return {"files": session().list_files(prefix)}
    return list_files
