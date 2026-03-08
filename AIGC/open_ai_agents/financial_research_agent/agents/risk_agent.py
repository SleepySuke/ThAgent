from agents.extensions.models.litellm_model import LitellmModel
from pydantic import BaseModel

from agents import Agent

# A sub‑agent specializing in identifying risk factors or concerns.

import os



RISK_PROMPT = (
    "你是一名风险分析师，关注公司前景中的潜在警示信号。"
    "根据背景研究资料，就竞争威胁、监管问题、供应链困难或增长放缓等风险因素撰写简短分析。"
    "请控制在两段以内。"
)

qwen_api_key = ""
qwen_model = LitellmModel(model="dashscope/qwen-plus-2025-12-01", api_key=qwen_api_key)


class AnalysisSummary(BaseModel):
    summary: str
    """Short text summary for this aspect of the analysis."""


risk_agent = Agent(
    name="RiskAnalystAgent",
    instructions=RISK_PROMPT,
    #output_type=AnalysisSummary,
    model=qwen_model,
)
