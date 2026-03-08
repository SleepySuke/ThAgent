from agents import Agent, WebSearchTool, function_tool
from agents.extensions.models.litellm_model import LitellmModel

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Add visual separators for better log readability
def log_separator():
    logger.info("=" * 60)

log_separator()
logger.info("FinancialSearchAgent initialized with enhanced logging")
log_separator()

# 创建带日志记录的搜索工具
web_search_tool = WebSearchTool()

@function_tool(
    name_override="web_search",
    description_override="Search the web for information and return search results"
)
async def logged_web_search(query: str) -> str:
    log_separator()
    logger.info("🔍 [TOOL START] WebSearchTool 正在调用")
    logger.info(f"📋 [TOOL PARAM] 查询内容: {query}")
    logger.info(f"⏰ [TOOL TIME] 调用时间: {logging.Formatter('%Y-%m-%d %H:%M:%S').format(logging.LogRecord('', 0, '', 0, '', (), None))}")
    log_separator()
    
    try:
        result = await web_search_tool(query)
        
        log_separator()
        logger.info("✅ [TOOL SUCCESS] WebSearchTool 调用成功")
        logger.info(f"📊 [TOOL STATS] 返回结果长度: {len(str(result))} 字符")
        logger.info(f"📝 [TOOL RESULT] 返回内容预览:")
        logger.info(f"   {str(result)[:500]}...")
        log_separator()
        
        return result
    except Exception as e:
        log_separator()
        logger.error(f"❌ [TOOL ERROR] WebSearchTool 调用失败: {e}")
        log_separator()
        raise

# Given a search term, use web search to pull back a brief summary.
# Summaries should be concise but capture the main financial points.

import os
INSTRUCTIONS = (
    "你是一名专注于金融领域的研究助理。"
    "根据给定的搜索词，利用网络搜索获取最新的背景信息，并生成一段不超过300词的简短摘要。"
    "重点关注对财务分析师有用的关键数字、事件或引述。"

)

qwen_api_key = ""
qwen_model = LitellmModel(model="dashscope/qwen-plus-2025-12-01", api_key=qwen_api_key)

search_agent = Agent(
    name="FinancialSearchAgent",
    model=qwen_model,
    instructions=INSTRUCTIONS,
    tools=[logged_web_search],
    # tools=[WebSearchTool()]
)
