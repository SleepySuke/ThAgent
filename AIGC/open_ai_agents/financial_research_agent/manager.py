from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Sequence

from rich.console import Console

from agents import Runner, custom_span, gen_trace_id, trace

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

def log_separator():
    logger.info("=" * 60)

# 所有子 Agent 均已移除 output_type，直接导入即可
from .agents.financials_agent import financials_agent
from .agents.planner_agent import FinancialSearchItem, FinancialSearchPlan, planner_agent
from .agents.risk_agent import risk_agent
from .agents.search_agent import search_agent
from .agents.verifier_agent import verifier_agent   # verifier_agent 也需改为纯文本输出（见下文）
from .agents.writer_agent import writer_agent       # writer_agent 已改为纯文本输出
from .printer import Printer


class FinancialResearchManager:
    """
    Orchestrates the full flow: planning, searching, sub‑analysis, writing, and verification.
    Compatible with DashScope (Tongyi Qianwen) – no output_type, no tool calls.
    """

    def __init__(self) -> None:
        self.console = Console()
        self.printer = Printer(self.console)

    async def run(self, query: str) -> None:
        trace_id = gen_trace_id()
        with trace("Financial research trace", trace_id=trace_id):
            self.printer.update_item(
                "trace_id",
                f"View trace: https://platform.openai.com/traces/trace?trace_id={trace_id}",
                is_done=True,
                hide_checkmark=True,
            )
            self.printer.update_item("start", "Starting financial research...", is_done=True)

            search_plan = await self._plan_searches(query)
            search_results = await self._perform_searches(search_plan)
            report_text = await self._write_report(query, search_results)   # 返回纯文本
            verification_text = await self._verify_report(report_text)     # 返回纯文本

            # 从报告中提取摘要和后续问题（辅助方法见后）
            short_summary = self._extract_summary(report_text)
            follow_ups = self._extract_follow_ups(report_text)

            final_report = f"Report summary\n\n{short_summary}"
            self.printer.update_item("final_report", final_report, is_done=True)
            self.printer.end()

        # 打印最终结果
        print("\n\n===== REPORT =====\n\n")
        print(report_text)
        print("\n\n===== FOLLOW-UP QUESTIONS =====\n\n")
        if follow_ups:
            print("\n".join(f"- {q}" for q in follow_ups))
        else:
            print("无")
        print("\n\n===== VERIFICATION =====\n\n")
        print(verification_text)

    # ---------- 规划搜索（已兼容 DashScope）----------
    async def _plan_searches(self, query: str) -> FinancialSearchPlan:
        self.printer.update_item("planning", "Planning searches...")
        result = await Runner.run(planner_agent, f"Query: {query}")

        raw_output = result.final_output
        self.printer.update_item("planning", f"Raw planner output: {raw_output[:200]}...", is_done=False)

        # 尝试提取 JSON
        json_match = re.search(r'```json\s*(\{.*?\})\s*```', raw_output, re.DOTALL)
        if not json_match:
            json_match = re.search(r'(\{.*\})', raw_output, re.DOTALL)

        if json_match:
            json_str = json_match.group(1)
            try:
                data = json.loads(json_str)
                searches_data = data.get("searches", [])
                items = [FinancialSearchItem(**item) for item in searches_data]
                plan = FinancialSearchPlan(searches=items)
                self.printer.update_item(
                    "planning",
                    f"Will perform {len(plan.searches)} searches",
                    is_done=True,
                )
                return plan
            except Exception as e:
                self.printer.update_item(
                    "planning",
                    f"JSON parsing failed: {e}, falling back to default plan",
                    is_done=True,
                )

        # 降级默认计划
        self.printer.update_item(
            "planning",
            "Failed to parse planner output, using default search terms",
            is_done=True,
        )
        return FinancialSearchPlan(
            searches=[
                FinancialSearchItem(
                    reason="默认搜索：公司最新财报",
                    query=f"{query} 财报",
                ),
                FinancialSearchItem(
                    reason="默认搜索：公司近期新闻",
                    query=f"{query} 新闻",
                ),
            ]
        )

    # ---------- 执行搜索 ----------
    async def _perform_searches(self, search_plan: FinancialSearchPlan) -> Sequence[str]:
        with custom_span("Search the web"):
            self.printer.update_item("searching", "Searching...")
            tasks = [asyncio.create_task(self._search(item)) for item in search_plan.searches]
            results: list[str] = []
            num_completed = 0
            for task in asyncio.as_completed(tasks):
                result = await task
                if result is not None:
                    results.append(result)
                num_completed += 1
                self.printer.update_item(
                    "searching", f"Searching... {num_completed}/{len(tasks)} completed"
                )
            self.printer.mark_item_done("searching")
            return results

    async def _search(self, item: FinancialSearchItem) -> str | None:
        input_data = f"Search term: {item.query}\nReason: {item.reason}"
        
        log_separator()
        logger.info("🚀 [SEARCH START] 开始新的搜索任务")
        logger.info(f"📋 [SEARCH QUERY] 搜索词: {item.query}")
        logger.info(f"🎯 [SEARCH REASON] 搜索原因: {item.reason}")
        log_separator()
        
        try:
            logger.info(f"🤖 [AGENT CALL] 正在调用 search_agent...")
            logger.info(f"📥 [AGENT INPUT] 输入数据: {input_data[:150]}...")
            
            result = await Runner.run(search_agent, input_data)
            output = str(result.final_output)
            
            log_separator()
            logger.info("✅ [AGENT SUCCESS] search_agent 调用成功")
            logger.info(f"📊 [AGENT STATS] 返回结果长度: {len(output)} 字符")
            logger.info(f"📝 [AGENT RESULT] 返回内容预览:")
            logger.info(f"   {output[:300]}...")
            log_separator()
            
            return output
        except Exception as e:
            log_separator()
            logger.error(f"❌ [SEARCH ERROR] 搜索任务失败")
            logger.error(f"🔴 [ERROR DETAILS] 查询: '{item.query}'")
            logger.error(f"🔴 [ERROR DETAILS] 错误信息: {e}")
            log_separator()
            return None

    # ---------- 撰写报告（手动调用子 agent）----------
    async def _write_report(self, query: str, search_results: Sequence[str]) -> str:
        self.printer.update_item("writing", "Running fundamental analysis...")
        search_text = "\n\n".join(search_results)

        # 1. 基本面分析
        fund_result = await Runner.run(
            financials_agent,
            f"基于以下搜索结果，分析公司的财务表现：\n{search_text}"
        )
        fund_summary = fund_result.final_output

        # 2. 风险分析
        self.printer.update_item("writing", "Running risk analysis...")
        risk_result = await Runner.run(
            risk_agent,
            f"基于以下搜索结果，分析公司的潜在风险：\n{search_text}"
        )
        risk_summary = risk_result.final_output

        # 3. 构建 writer 输入
        enhanced_input = (
            f"## 原始查询\n{query}\n\n"
            f"## 网络搜索结果摘要\n{search_text}\n\n"
            f"## 基本面分析\n{fund_summary}\n\n"
            f"## 风险分析\n{risk_summary}\n\n"
            "请根据以上所有信息，撰写一份完整的 Markdown 财务分析报告。\n"
            "报告必须包含以下部分：\n"
            "- **执行摘要**（2-3句话）\n"
            "- **详细分析**（至少3段）\n"
            "- **后续问题**（3-5个建议进一步研究的问题，每行以「- 」开头）"
        )

        self.printer.update_item("writing", "Writing final report...")
        result = await Runner.run(writer_agent, enhanced_input)
        self.printer.mark_item_done("writing")
        return result.final_output

    # ---------- 验证报告（纯文本）----------
    async def _verify_report(self, report_text: str) -> str:
        self.printer.update_item("verifying", "Verifying report...")
        result = await Runner.run(
            verifier_agent,
            f"请验证以下财务分析报告的内部一致性、来源清晰度，并指出任何问题或不确定之处：\n\n{report_text}"
        )
        self.printer.mark_item_done("verifying")
        return result.final_output   # 返回纯文本验证结果

    # ---------- 辅助解析方法（从 Markdown 提取摘要和后续问题）----------
    def _extract_summary(self, report: str) -> str:
        """从报告中提取执行摘要（简单正则）"""
        # 匹配「**执行摘要**」或「## 执行摘要」下方的内容
        match = re.search(
            r'(?:执行摘要|Executive Summary)[：:]\s*(.+?)(?=\n\n|\n##|\Z)',
            report,
            re.DOTALL | re.IGNORECASE
        )
        if match:
            return match.group(1).strip()
        return "无执行摘要"

    def _extract_follow_ups(self, report: str) -> list[str]:
        """从报告中提取后续问题（以「- 」开头的行）"""
        questions = []
        in_followup = False
        for line in report.split('\n'):
            if re.search(r'(?:后续问题|Follow-up Questions|Follow up)', line, re.IGNORECASE):
                in_followup = True
                continue
            if in_followup:
                if line.strip().startswith('- '):
                    questions.append(line.strip()[2:])
                elif line.strip() == '':
                    continue
                else:
                    # 遇到其他非空行，结束
                    if line.strip():
                        break
        return questions
