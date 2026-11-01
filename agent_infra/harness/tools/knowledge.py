"""T 层：知识检索工具（拉通道）。agent 在 ReAct loop 内按需调用。

推通道（recall 注入）覆盖冷启动；agent 中途想起的问题走本工具运行时检索。
KnowledgeBase 进程内单例（惰性），embedding 缓存保证重复调用近零 API。
"""
from __future__ import annotations

import asyncio

from harness.contract import RunContext
from harness.knowledge import KnowledgeBase
from harness.tools._base import _SPECS, _wrap

_KB: KnowledgeBase | None = None


def _kb() -> KnowledgeBase:
    global _KB  # noqa: PLW0603 —— 与 agent_server._MANAGER 同款模块级注入
    if _KB is None:
        from harness.config import runs_root

        _KB = KnowledgeBase(runs_root())
    return _KB


def search_knowledge(run: RunContext, session) -> callable:
    @_wrap(_SPECS["search_knowledge"])  # network 工具：30s deadline（矩阵 #15）
    async def search_knowledge(query: str, top_k: int = 3) -> str:
        """检索团队知识库（规范详情、历史方案、API 说明等非结构化文档）。

        Args:
            query: 检索关键词或问题（中文自然语言即可）。
            top_k: 返回条数，默认 3。
        """
        q = (query or "").strip()
        if not q:
            return "(query 为空：请给出具体检索词)"  # 矩阵 #7
        try:
            # to_thread：search 内含 litellm embed 的网络等待（非 Tfidf 路径
            # pool.submit(asyncio.run).result()）——同步阻塞段会冻结事件循环，
            # 让并行工具调用串行化且 deadline 掐不断（t3-rev Important）
            hits = await asyncio.to_thread(_kb().search, q, top_k)
        except Exception as e:  # 矩阵 #10：错误文本回模型，run 不死
            # 附根因（e.__cause__ or e）：trace 里直接可见 zai 报的真实错误
            #（auth/quota/模型名），不用翻服务端日志
            return f"(知识库检索失败: {e.__cause__ or e})"
        if not hits:
            return "(知识库无命中：换关键词重试，或用 request_human 问人)"
        return "\n\n".join(
            f"[{i + 1}] {h['path']} (score={h['score']:.3f})\n{h['snippet']}"
            for i, h in enumerate(hits))
    # 内层函数名即工具名（ADK FunctionTool 靠 __name__ 标识），必须与白名单一致
    return search_knowledge
