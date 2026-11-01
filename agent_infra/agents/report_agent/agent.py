"""Report Agent 组装：全链执行结论 + artifacts → 人读的 execution_report.md。"""
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
    model = resolve_model("report_agent", "zai/glm-4.6")
    register_model_capabilities()
    llm_kwargs = ({"extra_body": {"thinking": {"type": "disabled"}}}
                  if model.startswith("zai/glm-4") else {})
    return LlmAgent(
        name="report_agent",
        model=LiteLlm(model=model, **llm_kwargs),
        instruction=(_AGENT_DIR / "prompt.md").read_text(encoding="utf-8"),
        description="汇总全链执行结论产出人读的执行报告（execution_report.md）",
        tools=build_tools(run, manager, ["read_artifact"]),
        **build_callbacks(run, policy),
    )
