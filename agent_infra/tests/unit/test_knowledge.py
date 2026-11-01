"""知识层单测：LiteLlmEmbedder（Task 1）与 KnowledgeBase（Task 2 追加）。"""
import json
import math
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from harness.knowledge import (
    KnowledgeBase,
    LiteLlmEmbedder,
    build_embedder,
    chunk_text,
    embedding_model,
)
from harness.memory import TfidfEmbedder


def _fake_aembedding(scripts):
    """脚本化 litellm.aembedding 替身：按调用次序回放（每批同向量 / 抛异常）。"""
    calls: list[list[str]] = []

    async def aembedding(model, input):
        calls.append(list(input))
        step = scripts[min(len(calls) - 1, len(scripts) - 1)]
        if isinstance(step, Exception):
            raise step
        return {"data": [{"embedding": step} for _ in input]}

    return aembedding, calls


def test_embed_normalizes_and_records_dim(tmp_path):
    aemb, calls = _fake_aembedding([[3.0, 4.0]])
    e = LiteLlmEmbedder("zai/glm-embedding-3", tmp_path / "c.json",
                        aembedding=aemb)
    v = e.embed(["hello"])[0]
    assert abs(sum(w * w for w in v.values()) - 1.0) < 1e-9  # L2 归一（dot 即 cosine）
    assert e.dim == 2                                        # 维度记录（索引头用）
    assert calls == [["hello"]]


def test_cache_hit_skips_api(tmp_path):
    aemb, calls = _fake_aembedding([[0.1, 0.2]])
    cache = tmp_path / "c.json"
    LiteLlmEmbedder("m", cache, aembedding=aemb).embed(["共享文本"])
    LiteLlmEmbedder("m", cache, aembedding=aemb).embed(["共享文本"])  # 新实例读盘缓存
    assert len(calls) == 1                                   # 命中缓存零 API 调用
    keys = json.loads(cache.read_text(encoding="utf-8"))
    assert len(keys) == 1 and len(next(iter(keys))) == 64    # 缓存键是 sha256 hex


def test_retry_then_raise_after_two_retries(tmp_path):  # 矩阵 #1
    aemb, calls = _fake_aembedding([RuntimeError("rate limit")])
    e = LiteLlmEmbedder("m", tmp_path / "c.json", aembedding=aemb, backoff_s=0)
    with pytest.raises(RuntimeError, match="embedding failed"):
        e.embed(["x"])
    assert len(calls) == 3                                   # 1 + 2 次重试


def test_retry_succeeds_on_second_attempt(tmp_path):
    aemb, calls = _fake_aembedding([RuntimeError("timeout"), [1.0]])
    e = LiteLlmEmbedder("m", None, aembedding=aemb, backoff_s=0)
    v = e.embed(["x"])
    assert len(calls) == 2 and len(v[0]) == 1                # 瞬时失败重试可救


def test_readonly_cache_dir_still_embeds(tmp_path):  # 矩阵 #6
    aemb, _ = _fake_aembedding([[0.5]])
    ro = tmp_path / "ro"
    ro.mkdir()
    os.chmod(ro, 0o500)
    try:
        e = LiteLlmEmbedder("m", ro / "c.json", aembedding=aemb)
        assert e.embed(["x"])[0]                             # 写盘失败被吞，功能不中断
    finally:
        os.chmod(ro, 0o700)


def test_build_embedder_degrades_without_key(monkeypatch, tmp_path):  # 矩阵 #2
    # V2 申报（2026-10-14）：接语义 embedding 后 .env 带 DASHSCOPE key/model，
    # litellm 的 load_dotenv 会把它注入进程环境——降级测试必须清全部 key 与
    # 模型覆盖，否则全套顺序下（test_config 先 import litellm）必红
    monkeypatch.delenv("ZAI_API_KEY", raising=False)
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.delenv("AGENT_INFRA_EMBEDDING_MODEL", raising=False)
    assert isinstance(build_embedder(tmp_path / "c.json"), TfidfEmbedder)


def test_build_embedder_uses_litellm_with_key(monkeypatch, tmp_path):
    # openai 兼容路由（默认）需要 ZAI_API_BASE 显式指向 + ZAI_API_KEY
    monkeypatch.setenv("ZAI_API_KEY", "x")
    monkeypatch.setenv("ZAI_API_BASE", "https://example/api")
    assert isinstance(build_embedder(tmp_path / "c.json"), LiteLlmEmbedder)


def test_embedding_model_env_override(monkeypatch):
    monkeypatch.setenv("AGENT_INFRA_EMBEDDING_MODEL",
                       "openai/text-embedding-3-small")
    assert embedding_model() == "openai/text-embedding-3-small"


class _CharBagEmbedder:
    """确定性字符袋嵌入（跨批次一致，vocab 下标=ord 取模）：测检索排序用。"""

    def embed(self, texts):
        out = []
        for t in texts:
            counts: dict[int, float] = {}
            for ch in t:
                if not ch.isspace():
                    k = ord(ch) % 8192
                    counts[k] = counts.get(k, 0.0) + 1.0
            norm = math.sqrt(sum(v * v for v in counts.values())) or 1.0
            out.append({k: v / norm for k, v in counts.items()})
        return out


class _Counting:
    """包装任意 embedder 计数（嵌入文本条数）。"""

    def __init__(self, inner):
        self.inner, self.calls = inner, 0

    def embed(self, texts):
        self.calls += len(texts)
        return self.inner.embed(texts)


def _corpus(tmp_path: Path, docs: dict[str, str]) -> Path:
    d = tmp_path / "knowledge"
    d.mkdir()
    for name, text in docs.items():
        (d / name).write_text(text, encoding="utf-8")
    return d


def test_chunk_text_slides_window_with_overlap():
    text = "# 标题\n" + "甲" * 600
    chunks = chunk_text(text)
    assert len(chunks) == 2                        # 604 字 → 500 窗 + 尾窗
    assert len(chunks[0]["text"]) == 500
    assert chunks[1]["text"][:50] == "甲" * 50     # 50 字重叠
    assert chunks[1]["title"] == "标题"            # 尾窗携带最近标题
    assert chunks[0]["title"] == ""                # 首窗标题在正文内，不重复注


def test_search_ranks_relevant_doc_first(tmp_path):
    corpus = _corpus(tmp_path, {
        "alpha.md": "# 阿尔法规范\n西湖龙井茶树修剪注意事项若干条",
        "beta.md": "# 贝塔规范\nKubernetes 集群节点漂移排查手册",
    })
    kb = KnowledgeBase(tmp_path / "runs", corpus, embedder=_CharBagEmbedder())
    hits = kb.search("茶树修剪")
    assert hits and hits[0]["path"] == "alpha.md"
    assert set(hits[0]) == {"path", "score", "snippet"}


def test_search_empty_query_no_api(tmp_path):  # 矩阵 #7
    corpus = _corpus(tmp_path, {"a.md": "内容"})
    emb = _Counting(_CharBagEmbedder())
    kb = KnowledgeBase(tmp_path / "runs", corpus, embedder=emb)
    assert kb.search("   ") == []
    assert emb.calls == 0                          # 空 query 连索引都不建


def test_search_empty_corpus_returns_empty(tmp_path):  # 矩阵 #4
    kb = KnowledgeBase(tmp_path / "runs", tmp_path / "nope",
                       embedder=_CharBagEmbedder())
    assert kb.search("任何") == []


def test_search_topk_beyond_chunks_returns_all(tmp_path):  # 矩阵 #8
    corpus = _corpus(tmp_path, {"a.md": "唯一文档"})
    kb = KnowledgeBase(tmp_path / "runs", corpus, embedder=_CharBagEmbedder())
    assert len(kb.search("文档", top_k=99)) >= 1   # 不越界


def test_index_rebuilt_when_source_mtime_changes(tmp_path):  # 矩阵 #5
    corpus = _corpus(tmp_path, {"a.md": "原文"})
    runs = tmp_path / "runs"
    emb = _Counting(_CharBagEmbedder())
    KnowledgeBase(runs, corpus, embedder=emb).search("原文")
    n1 = emb.calls
    future = time.time() + 10
    os.utime(corpus / "a.md", (future, future))
    KnowledgeBase(runs, corpus, embedder=emb).search("原文")  # 新实例：读盘上索引
    assert emb.calls > n1                          # mtime 漂移 → 重嵌


def test_corrupt_index_rebuilt_and_valid(tmp_path):  # 矩阵 #3
    corpus = _corpus(tmp_path, {"a.md": "折扣率上限 20%"})
    runs = tmp_path / "runs"
    KnowledgeBase(runs, corpus, embedder=_CharBagEmbedder()).search("上限")
    idx_path = runs / "knowledge" / "knowledge_index.json"
    idx_path.write_text("{corrupted", encoding="utf-8")   # 模拟半写
    hits = KnowledgeBase(runs, corpus, embedder=_CharBagEmbedder()).search("上限")
    assert hits and hits[0]["path"] == "a.md"      # 损坏 → 静默重建
    idx = json.loads(idx_path.read_text(encoding="utf-8"))
    assert idx["chunks"]                           # 重建后索引完好
    assert not list((runs / "knowledge").glob("*.tmp"))  # 原子写无残留


def test_model_mismatch_triggers_rebuild(tmp_path):  # 矩阵 #12
    corpus = _corpus(tmp_path, {"a.md": "文本"})
    runs = tmp_path / "runs"
    KnowledgeBase(runs, corpus, embedder=_CharBagEmbedder()).search("文本")
    idx_path = runs / "knowledge" / "knowledge_index.json"
    idx = json.loads(idx_path.read_text(encoding="utf-8"))
    idx["model"] = "旧模型/x"                      # 模拟换 embedding 模型后残留
    idx_path.write_text(json.dumps(idx, ensure_ascii=False), encoding="utf-8")
    emb = _Counting(_CharBagEmbedder())
    KnowledgeBase(runs, corpus, embedder=emb).search("文本")
    assert emb.calls > 0                           # 模型变更 → 整体重建


def test_concurrent_rebuild_keeps_valid_index(tmp_path):  # 矩阵 #13
    corpus = _corpus(tmp_path, {"a.md": "并发重建" + "字" * 600})
    runs = tmp_path / "runs"
    kbs = [KnowledgeBase(runs, corpus, embedder=_CharBagEmbedder())
           for _ in range(2)]
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda kb: kb.search("重建"), kbs))
    idx = json.loads(
        (runs / "knowledge" / "knowledge_index.json").read_text(encoding="utf-8"))
    assert idx["chunks"]                           # 后写者覆盖无害，索引恒为合法 JSON


def test_search_raises_when_embedding_fails(tmp_path):  # 矩阵 #1/#9：失败上抛
    corpus = _corpus(tmp_path, {"a.md": "文本"})

    class _Boom:
        def embed(self, texts):
            raise RuntimeError("embedding down")

    kb = KnowledgeBase(tmp_path / "runs", corpus, embedder=_Boom())
    with pytest.raises(RuntimeError, match="embedding down"):
        kb.search("文本")


def test_tfidf_joint_embedding_path(tmp_path):
    # TfidfEmbedder 是 batch-local IDF：query 必须与 chunk 同批嵌入才可比
    corpus = _corpus(tmp_path, {
        "tea.md": "# 茶规范\n龙井茶树修剪口诀",
        "k8s.md": "# 运维手册\n集群节点漂移排查",
    })
    kb = KnowledgeBase(tmp_path / "runs", corpus, embedder=TfidfEmbedder())
    assert kb.search("茶树修剪")[0]["path"] == "tea.md"


def test_semantic_path_embeds_query_only(tmp_path):
    # 语义嵌入（非 Tfidf）跨批一致：索引建好后 search 只嵌 query（缓存后近零成本）
    corpus = _corpus(tmp_path, {"a.md": "长文档" + "字" * 600})
    emb = _Counting(_CharBagEmbedder())
    kb = KnowledgeBase(tmp_path / "runs", corpus, embedder=emb)
    kb.search("文档")
    built = emb.calls
    kb.search("查询")
    assert emb.calls == built + 1
