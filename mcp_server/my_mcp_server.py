# -*- coding: UTF-8 -*-
'''
@Author ：自然醒
@Version ：1.0
'''

import asyncio
import json
import os
import sys
from dotenv import load_dotenv

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(ENV_PATH)

def log_debug(msg):
    print(msg, file=sys.stderr, flush=True)

log_debug(f"Loading .env from: {ENV_PATH}")
log_debug(f"DASHSCOPE_API_KEY set: {'DASHSCOPE_API_KEY' in os.environ}")

# MCP Server Imports
from mcp import types as mcp_types
from mcp.server.lowlevel import Server, NotificationOptions
from mcp.server.models import InitializationOptions
import mcp.server.stdio

# ADK Tool Imports
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.load_web_page import load_web_page
from google.adk.tools.mcp_tool.conversion_utils import adk_to_mcp_tool_type

log_debug("Initializing ADK load_web_page tool...")
adk_tool_to_expose = FunctionTool(load_web_page)
log_debug(f"ADK tool '{adk_tool_to_expose.name}' initialized and ready to be exposed via MCP.")

log_debug("Creating MCP Server instance...")
# Create a named MCP Server instance using the mcp.server library
app = Server("adk-tool-exposing-mcp-server")

# Implement the MCP server's handler to list available tools
@app.list_tools()
async def list_mcp_tools() -> list[mcp_types.Tool]:
    """MCP handler to list tools this server exposes."""
    log_debug("MCP Server: Received list_tools request.")
    mcp_tool_schema = adk_to_mcp_tool_type(adk_tool_to_expose)
    log_debug(f"MCP Server: Advertising tool: {mcp_tool_schema.name}")
    return [mcp_tool_schema]

@app.call_tool()
async def call_mcp_tool(
    name: str, arguments: dict
) -> list[mcp_types.Content]:
    """MCP handler to execute a tool call requested by an MCP client."""
    log_debug(f"MCP Server: Received call_tool request for '{name}' with args: {arguments}")

    if name == adk_tool_to_expose.name:
        try:
            adk_tool_response = await adk_tool_to_expose.run_async(
                args=arguments,
                tool_context=None,
            )
            log_debug(f"MCP Server: ADK tool '{name}' executed. Response: {adk_tool_response}")
            response_text = json.dumps(adk_tool_response, indent=2)
            return [mcp_types.TextContent(type="text", text=response_text)]

        except Exception as e:
            log_debug(f"MCP Server: Error executing ADK tool '{name}': {e}")
            error_text = json.dumps({"error": f"Failed to execute tool '{name}': {str(e)}"})
            return [mcp_types.TextContent(type="text", text=error_text)]
    else:
        log_debug(f"MCP Server: Tool '{name}' not found/exposed by this server.")
        error_text = json.dumps({"error": f"Tool '{name}' not implemented by this server."})
        return [mcp_types.TextContent(type="text", text=error_text)]

async def run_mcp_stdio_server():
    """Runs the MCP server, listening for connections over standard input/output."""
    async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
        log_debug("MCP Stdio Server: Starting handshake with client...")
        await app.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name=app.name,
                server_version="0.1.0",
                capabilities=app.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )
        log_debug("MCP Stdio Server: Run loop finished or client disconnected.")

if __name__ == "__main__":
    log_debug("Launching MCP Server to expose ADK tools via stdio...")
    try:
        asyncio.run(run_mcp_stdio_server())
    except KeyboardInterrupt:
        log_debug("\nMCP Server (stdio) stopped by user.")
    except Exception as e:
        log_debug(f"MCP Server (stdio) encountered an error: {e}")
    finally:
        log_debug("MCP Server (stdio) process exiting.")