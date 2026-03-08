import asyncio

from ..auto_mode import input_with_fallback

from .manager import FinancialResearchManager


# Entrypoint for the financial bot example.
# Run this as `python -m examples.financial_research_agent.main` and enter a
# financial research query, for example:
# "Write up an analysis of Apple Inc.'s most recent quarter."
async def main() -> None:
    query = input_with_fallback(
        "请输入你要查询的语句: ",
        "写一份关于苹果公司最新季度的分析。",
    )
    mgr = FinancialResearchManager()
    await mgr.run(query)


if __name__ == "__main__":
    asyncio.run(main())
