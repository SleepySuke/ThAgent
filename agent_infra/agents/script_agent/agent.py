"""Script Agent 组装：读 case_list 产出可执行 pytest 测试脚本。

「LLM 生成脚本，确定性程序执行脚本」——Script 只负责生成（reuse 条目引用
既有用例、generate 条目写新函数），执行交给 Program 节点 case_executor。
三层 callback 同源（harness 通用供给）；接管八期退役的 testing_agent 职责。
"""
from __future__ import annotations

from pathlib import Path

from google.adk.agents import LlmAgent
from google.adk.models.lite_llm import LiteLlm

from harness.callbacks import build_callbacks
from harness.config import register_model_capabilities, resolve_model
from harness.contract import RunContext
from harness.policy import NodePolicy
from harness.sandbox.manager import SandboxManager
from harness.tools import build_tools

_AGENT_DIR = Path(__file__).parent


def build_agent(run: RunContext, manager: SandboxManager,
                policy: NodePolicy) -> LlmAgent:
    model = resolve_model("script_agent", "zai/glm-4.6")
    register_model_capabilities()
    llm_kwargs = ({"extra_body": {"thinking": {"type": "disabled"}}}
                  if model.startswith("zai/glm-4") else {})
    return LlmAgent(
        name="script_agent",
        model=LiteLlm(model=model, **llm_kwargs),
        instruction=(_AGENT_DIR / "prompt.md").read_text(encoding="utf-8"),
        description="读用例清单生成覆盖全部条目的可执行 pytest 测试脚本",
        tools=build_tools(run, manager,
                          ["read_artifact", "write_file", "read_file",
                           "list_files", "run_cmd"]),
        **build_callbacks(run, policy),
    )
