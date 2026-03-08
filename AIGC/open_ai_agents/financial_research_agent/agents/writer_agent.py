from agents.extensions.models.litellm_model import LitellmModel
from pydantic import BaseModel

from agents import Agent

# Writer agent brings together the raw search results and optionally calls out
# to sub‑analyst tools for specialized commentary, then returns a cohesive markdown report.

qwen_api_key = ""
qwen_model = LitellmModel(model="dashscope/qwen-plus-2025-12-01", api_key=qwen_api_key)
# WRITER_PROMPT = (
#     "你是一名高级财务分析师。你将获得原始查询请求以及一组原始搜索摘要。"
#     "你的任务是将这些信息整合成一份长篇Markdown报告（至少若干段落），"
#     "包括简短的执行摘要和后续问题。必要时，可调用可用的分析工具（如基本面分析、风险分析）"
#     "获取专家短评，并将其融入报告中。"
# )

WRITER_PROMPT = (
    "你是一名高级财务分析师。你将获得以下内容：\n"
    "1. 原始查询\n"
    "2. 网络搜索结果摘要\n"
    "3. 基本面分析摘要（已提供）\n"
    "4. 风险分析摘要（已提供）\n\n"
    "请综合以上信息，撰写一份完整的 Markdown 格式财务分析报告。\n"
    "报告必须包含以下部分：\n"
    "- **执行摘要**（2-3句话）\n"
    "- **详细分析**（至少3段）\n"
    "- **后续问题**（3-5个建议进一步研究的问题）\n\n"
    "在报告末尾，单独列出后续问题，每行一个，以「- 」开头。"
)


class FinancialReportData(BaseModel):
    short_summary: str
    """A short 2‑3 sentence executive summary."""

    markdown_report: str
    """The full markdown report."""

    follow_up_questions: list[str]
    """Suggested follow‑up questions for further research."""


# Note: We will attach handoffs to specialist analyst agents at runtime in the manager.
# This shows how an agent can use handoffs to delegate to specialized subagents.
writer_agent = Agent(
    name="FinancialWriterAgent",
    instructions=WRITER_PROMPT,
    model=qwen_model,
    #output_type=FinancialReportData,
)
