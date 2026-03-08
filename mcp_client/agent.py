# -*- coding: UTF-8 -*-
'''
@Author ：自然醒
@Version ：1.0
'''
import os
import sys
from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool import McpToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from mcp import StdioServerParameters
from google.adk.models.lite_llm import LiteLlm
from dotenv import load_dotenv

load_dotenv()

PATH_TO_YOUR_MCP_SERVER_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "mcp_server",
    "my_mcp_server.py"
)

root_agent = LlmAgent(
    model=LiteLlm(model="dashscope/qwen-plus"),
    name='web_reader_mcp_client_agent',
    instruction="Use the 'load_web_page' tool to fetch content from a URL provided by the user.",
    tools=[
        McpToolset(
            connection_params=StdioConnectionParams(
                server_params = StdioServerParameters(
                    command=sys.executable,
                    args=[PATH_TO_YOUR_MCP_SERVER_SCRIPT],
                )
            )
            # tool_filter=['load_web_page'] # Optional: ensure only specific tools are loaded
        )
    ],
)