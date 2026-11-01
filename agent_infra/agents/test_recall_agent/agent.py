"""Test Recall Agent 组装：CR 风险 → 知识检索 → 召回清单与覆盖缺口。"""
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
    model = resolve_model("test_recall_agent", "zai/glm-4.6")
    register_model_capabilities()
    llm_kwargs = ({"extra_body": {"thinking": {"type": "disabled"}}}
                  if model.startswith("zai/glm-4") else {})
    return LlmAgent(
        name="test_recall_agent",
        model=LiteLlm(model=model, **llm_kwargs),
        instruction=(_AGENT_DIR / "prompt.md").read_text(encoding="utf-8"),
        description="从变更风险检索既有测试用例，产出召回清单与覆盖缺口",
        tools=build_tools(run, manager, ["search_knowledge", "request_human"]),
        **build_callbacks(run, policy),
    )
