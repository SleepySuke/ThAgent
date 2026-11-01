"""BM25Scorer 与双腿融合单测（矩阵 #9）+ HybridMemory scorer 升级。"""
import json

from harness.knowledge import BM25Scorer, KnowledgeBase
from harness.memory import HybridMemory, TfidfEmbedder

DOCS = ["折扣率上限是 0.20 超过需运营审批", "金额计算必须用 Decimal 存储口径",
        "阶梯折扣档位变更要同步测试断言"]


def test_bm25_ranks_relevant_doc_first():
    s = BM25Scorer().score("折扣上限多少", DOCS)
    assert s[0] == max(s)                      # 相关文档得分最高
    assert s[1] == min(s)                      # Decimal 文档最不相关


def test_bm25_saturation_and_length_norm():
    # tf 饱和：同一词重复 10 次的 doc 不应线性碾压提及 1 次的 doc
    repetitive = "折扣 " * 10
    plain = "折扣上限"
    s = BM25Scorer().score("折扣", [repetitive.strip(), plain])
    assert s[0] < s[1] * 3                     # b=0.75 长度归一压制堆词
    # 长度归一：长 doc 与短 doc 同词频密度下不过分吃亏
    s2 = BM25Scorer().score("折扣", ["无关内容" * 50 + " 折扣", "折扣"])
    assert s2[0] < s2[1]


def test_bm25_empty_inputs():
    assert BM25Scorer().score("", DOCS) == [0.0, 0.0, 0.0]
    assert BM25Scorer().score("折扣", []) == []


def test_kb_rrf_fuses_two_legs(tmp_path):      # 矩阵 #9：两腿冲突 RRF 共识
    corpus = tmp_path / "knowledge"
    corpus.mkdir()
    (corpus / "a.md").write_text(
        "阶梯折扣档位变更要同步测试断言，档位边界 100 500 1000", encoding="utf-8")
    (corpus / "b.md").write_text("金额计算必须用 Decimal，汇率不实时拉取", encoding="utf-8")
    kb = KnowledgeBase(tmp_path, corpus, embedder=__import__(
        "harness.memory", fromlist=["TfidfEmbedder"]).TfidfEmbedder())
    hits = kb.search("阶梯折扣档位测试", top_k=2)
    assert [h["path"] for h in hits] == ["a.md", "b.md"]   # RRF 定序
    assert all(0.0 <= h["score"] <= 1.0 for h in hits)     # score 仍是 cosine 域（裁定 2）


def test_kb_single_leg_degrades_when_no_vectors(tmp_path):  # 矩阵 #9 后半
    corpus = tmp_path / "knowledge"
    corpus.mkdir()
    (corpus / "a.md").write_text("阶梯折扣档位变更要同步测试断言", encoding="utf-8")
    # 显式 Tfidf：密闭单测不烧 API（DashScope 欠费时默认 build_embedder 会
    # 走 LiteLlmEmbedder 打真实端点——env 有 key 就不再是无 LLM 的单测）
    kb = KnowledgeBase(tmp_path, corpus, embedder=TfidfEmbedder())
    kb._ensure_index()
    for c in kb._index["chunks"]:             # 抽掉向量：模拟向量腿不可用
        c.pop("vector", None)
    class _NoVec:                             # 非 Tfidf 但无向量可点积 → 向量腿全 0
        model = "fake"
    kb.embedder = _NoVec()
    kb.embedder.embed = lambda texts: [{} for _ in texts]
    hits = kb.search("阶梯折扣", top_k=1)      # BM25 独撑，不炸
    assert hits and hits[0]["path"] == "a.md"


def test_hybrid_memory_scorer_replaces_tfidf_semantic(tmp_path):
    conv = tmp_path / "conv.json"
    conv.write_text(json.dumps([
        {"kind": "team_convention", "text": "金额计算必须用 Decimal 存储口径", "repo": "x"}],
        ensure_ascii=False), encoding="utf-8")
    mem = HybridMemory(tmp_path, conv, scorer=BM25Scorer())
    out = mem.recall(type("S", (), {"node_id": "cr_agent", "payload": {"repo": "x"},
                                    "context_id": "", "kinds": None})())
    assert out and "Decimal" in out[0]["content"]


def test_hybrid_memory_default_keeps_tfidf_path(tmp_path):   # 降级保留（回归）
    conv = tmp_path / "conv.json"
    conv.write_text(json.dumps([
        {"kind": "team_convention", "text": "金额计算必须用 Decimal 存储口径", "repo": "x"}],
        ensure_ascii=False), encoding="utf-8")
    mem = HybridMemory(tmp_path, conv)         # scorer=None → 既有 TF-IDF 路径
    assert mem.scorer is None
    out = mem.recall(type("S", (), {"node_id": "cr_agent", "payload": {"repo": "x"},
                                    "context_id": "", "kinds": None})())
    assert out                                 # 语义与七期前完全一致


def test_build_memory_defaults_to_bm25(tmp_path):
    from harness.memory import build_memory
    mem = build_memory(tmp_path, enabled=True)
    assert isinstance(mem.scorer, BM25Scorer)
