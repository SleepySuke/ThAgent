# -*- coding: UTF-8 -*-
"""
MCP 连接诊断脚本
"""
import os
import subprocess
import sys

print("=" * 50)
print("MCP 连接诊断")
print("=" * 50)

# 1. 检查路径
mcp_client_dir = os.path.dirname(os.path.abspath(__file__))
mcp_server_script = os.path.join(
    os.path.dirname(mcp_client_dir),
    "mcp_server",
    "my_mcp_server.py"
)

print(f"\n1. 路径检查:")
print(f"   - mcp_client 目录: {mcp_client_dir}")
print(f"   - mcp_server 脚本: {mcp_server_script}")
print(f"   - 脚本是否存在: {os.path.exists(mcp_server_script)}")

# 2. 检查 Python
print(f"\n2. Python 检查:")
print(f"   - Python 版本: {sys.version}")
print(f"   - Python 路径: {sys.executable}")

# 3. 检查 .env 文件
env_file = os.path.join(os.path.dirname(mcp_client_dir), "mcp_server", ".env")
print(f"\n3. .env 文件检查:")
print(f"   - .env 路径: {env_file}")
print(f"   - .env 存在: {os.path.exists(env_file)}")

# 4. 尝试导入必要的模块
print(f"\n4. 模块导入检查:")
modules_to_check = [
    "mcp",
    "mcp.server.stdio",
    "google.adk.tools.function_tool",
    "google.adk.tools.load_web_page",
    "dotenv"
]

for module in modules_to_check:
    try:
        __import__(module)
        print(f"   - {module}: OK")
    except ImportError as e:
        print(f"   - {module}: FAILED - {e}")

# 5. 尝试启动 mcp_server (仅初始化，不进行完整握手)
print(f"\n5. 尝试启动 MCP Server (简单测试):")
try:
    result = subprocess.run(
        [sys.executable, "-c", f"""
import sys
sys.path.insert(0, r'{os.path.dirname(mcp_client_dir)}')
from mcp_server.my_mcp_server import adk_tool_to_expose
print(f"Tool name: {{adk_tool_to_expose.name}}")
print("Import successful!")
"""],
        capture_output=True,
        text=True,
        timeout=10,
        cwd=os.path.dirname(mcp_client_dir)
    )
    print(f"   - 返回码: {result.returncode}")
    if result.stdout:
        print(f"   - stdout: {result.stdout[:500]}")
    if result.stderr:
        print(f"   - stderr: {result.stderr[:500]}")
except Exception as e:
    print(f"   - 错误: {e}")

print("\n" + "=" * 50)
print("诊断完成")
print("=" * 50)
