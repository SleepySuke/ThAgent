from agents.extensions.models.litellm_model import LitellmModel
from pydantic import BaseModel

from agents import Agent

# Agent to sanity‑check a synthesized report for consistency and recall.
# This can be used to flag potential gaps or obvious mistakes.
VERIFIER_PROMPT = (
    "你是一名细致入微的审计师。现收到一份财务分析报告，"
    "请验证该报告内部一致、来源清晰，且不包含无依据的断言。"
    "指出任何问题或不确定之处。"
)

qwen_api_key = ""
qwen_model = LitellmModel(model="dashscope/qwen-plus-2025-12-01", api_key=qwen_api_key)


class VerificationResult(BaseModel):
    verified: bool
    """Whether the report seems coherent and plausible."""

    issues: str
    """If not verified, describe the main issues or concerns."""


verifier_agent = Agent(
    name="VerificationAgent",
    instructions=VERIFIER_PROMPT,
    model=qwen_model,
    #output_type=VerificationResult,
)
