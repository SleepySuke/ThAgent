"""Planning/Controller Agent 组装：从死 DAG 选执行子集，产出 ExecutionPlan。

纯规划节点：无沙箱工具（不读 diff、不跑命令），唯一工具是向人提问
（request_human，需求模糊到无法选节点时用）。三层 callback 与 cr_agent 同源
（harness 通用供给），manager 参数仅保留统一签名供 A2A 加载按名分发。
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
    model = resolve_model("planning_agent", "zai/glm-4.6")
    register_model_capabilities()
    llm_kwargs = ({"extra_body": {"thinking": {"type": "disabled"}}}
                  if model.startswith("zai/glm-4") else {})
    return LlmAgent(
        name="planning_agent",
        model=LiteLlm(model=model, **llm_kwargs),
        instruction=(_AGENT_DIR / "prompt.md").read_text(encoding="utf-8"),
        description="编排规划：从死 DAG 选执行子集，产出 ExecutionPlan",
        tools=build_tools(run, manager, ["request_human"]),
        **build_callbacks(run, policy),
    )
