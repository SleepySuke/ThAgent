"""search_knowledge 工具：注册 + 检索文本化 + 空查询/错误契约（矩阵 #7/#10）。"""
from harness.contract import RunContext
from harness.knowledge import KnowledgeBase
from harness.memory import TfidfEmbedder
from harness.tools import FACTORIES
from harness.tools.knowledge import search_knowledge


def _kb(tmp_path):
    corpus = tmp_path / "knowledge"
    corpus.mkdir()
    (corpus / "discount-policy.md").write_text(
        "# 折扣规范\n全场促销折扣率上限 20%（rate <= 0.20）", encoding="utf-8")
    return KnowledgeBase(tmp_path / "runs", corpus, embedder=TfidfEmbedder())


def _tool(tmp_path, monkeypatch):
    from harness.tools import knowledge as tk

    monkeypatch.setattr(tk, "_KB", _kb(tmp_path))
    return search_knowledge(
        RunContext(trace_id="t", repo_path="x", commit="d"), None)


def test_registered_in_factories():
    assert "search_knowledge" in FACTORIES


async def test_tool_returns_hit_list(tmp_path, monkeypatch):
    out = await _tool(tmp_path, monkeypatch)("折扣率上限是多少")
    assert "discount-policy.md" in out and "0.20" in out
    assert "score=" in out                       # path + score + 摘要（设计 §2）


async def test_tool_empty_query_no_api(tmp_path, monkeypatch):  # 矩阵 #7
    assert "为空" in await _tool(tmp_path, monkeypatch)("   ")


async def test_tool_error_text_not_raise(tmp_path, monkeypatch):  # 矩阵 #10
    from harness.tools import knowledge as tk

    class _Boom:
        def search(self, q, top_k=3):
            raise RuntimeError("kb down")

    monkeypatch.setattr(tk, "_KB", _Boom())
    tool = search_knowledge(
        RunContext(trace_id="t", repo_path="x", commit="d"), None)
    assert "检索失败" in await tool("任何")     # 错误文本回模型，不炸 run
