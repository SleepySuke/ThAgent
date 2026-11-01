"""Requirement Agent 组装：需求/commit → 结构化任务说明（cr 的上游增益）。"""
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
    # 两级模型解析：AGENT_INFRA_MODEL_REQUIREMENT_AGENT > AGENT_INFRA_MODEL > 默认
    model = resolve_model("requirement_agent", "zai/glm-4.6")
    register_model_capabilities()
    llm_kwargs = ({"extra_body": {"thinking": {"type": "disabled"}}}
                  if model.startswith("zai/glm-4") else {})
    return LlmAgent(
        name="requirement_agent",
        model=LiteLlm(model=model, **llm_kwargs),
        instruction=(_AGENT_DIR / "prompt.md").read_text(encoding="utf-8"),
        description="把需求与 commit 改动翻译成结构化任务说明（类型/范围/风险/验收）",
        tools=build_tools(run, manager,
                          ["read_diff", "read_file", "list_files"]),
        **build_callbacks(run, policy),
    )
