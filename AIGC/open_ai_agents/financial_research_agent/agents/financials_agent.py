from agents.extensions.models.litellm_model import LitellmModel
from pydantic import BaseModel

from agents import Agent

qwen_api_key = ""
qwen_model = LitellmModel(model="dashscope/qwen-plus-2025-12-01", api_key=qwen_api_key)

# import os


# A sub‑agent focused on analyzing a company's fundamentals.
FINANCIALS_PROMPT = (
    "你是一名专注于公司基本面（如收入、利润、利润率及增长轨迹）的财务分析师。"
    "给定关于某公司的网页（以及可选的文档）搜索结果合集，请撰写一份关于其近期财务表现的精炼分析。"
    "提取关键指标或引述。请控制在两段以内。"
)


class AnalysisSummary(BaseModel):
    summary: str
    """Short text summary for this aspect of the analysis."""


financials_agent = Agent(
    name="FundamentalsAnalystAgent",
    instructions=FINANCIALS_PROMPT,
    #output_type=AnalysisSummary,
    model=qwen_model,
)
