from agents.extensions.models.litellm_model import LitellmModel
from pydantic import BaseModel

from agents import Agent

# Generate a plan of searches to ground the financial analysis.
# For a given financial question or company, we want to search for
# recent news, official filings, analyst commentary, and other
# relevant background.

import os

PROMPT = (
    "你是一名财务研究规划师。针对给定的财务分析请求，制定一组网络搜索任务。\n"
    "输出格式必须严格遵循以下 JSON 结构，不要包含任何其他文字、解释或 markdown：\n"
    '{\n  "searches": [\n    {\n      "reason": "搜索理由",\n      "query": "搜索词"\n    }\n  ]\n}\n'
    "请输出 5 到 15 个搜索项。"
)

# PROMPT = (
#     "你是一名财务研究规划师。针对给定的财务分析请求，制定一组网络搜索任务，以收集所需的上下文信息。"
#     "目标应包含近期的头条新闻、财报电话会议或10‑K文件摘要、分析师评论以及行业背景。"
#     "请输出5至15个待查询的搜索词。"
# )

qwen_api_key = ""
qwen_model = LitellmModel(model="dashscope/qwen-plus-2025-12-01", api_key=qwen_api_key)


class FinancialSearchItem(BaseModel):
    reason: str
    """Your reasoning for why this search is relevant."""

    query: str
    """The search term to feed into a web (or file) search."""


class FinancialSearchPlan(BaseModel):
    searches: list[FinancialSearchItem]
    """A list of searches to perform."""


planner_agent = Agent(
    name="FinancialPlannerAgent",
    instructions=PROMPT,
    model=qwen_model,
    #output_type=FinancialSearchPlan,
)
