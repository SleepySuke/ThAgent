import json
from pathlib import Path

import pytest

from harness.contract import AgentOutput
from harness.knowledge import KnowledgeBase
from harness.memory import (
    HybridMemory,
    NoopMemory,
    RecallSpec,
    TfidfEmbedder,
    _cosine,
    _rrf,
    build_memory,
)


def test_noop_memory_accepts_extended_record():
    m = NoopMemory()
    m.record("t", None, context_id="c", commit="d")  # 不抛
    m.record("t", AgentOutput({"issues": []}, "", "ok"))


def test_recall_spec_defaults():
    s = RecallSpec(node_id="cr", payload={})
    assert s.kinds is None
    assert s.context_id == ""


def test_recall_spec_kinds_settable():
    s = RecallSpec(node_id="cr", payload={},
                   context_id="repo:x", kinds=frozenset({"team_convention"}))
    assert s.context_id == "repo:x"
    assert s.kinds == frozenset({"team_convention"})


def test_tfidf_similar_texts_score_higher():
    e = TfidfEmbedder()
    v = e.embed(["bare except 吞异常", "bare except swallows", "order discount"])
    assert _cosine(v[0], v[1]) > _cosine(v[0], v[2])


def test_tfidf_vectors_unit_normalized():
    e = TfidfEmbedder()
    v = e.embed(["hello world"])[0]
    assert abs(sum(w * w for w in v.values()) - 1.0) < 1e-9


def test_cosine_zero_on_empty():
    assert _cosine({}, {1: 0.5}) == 0.0


def test_rrf_fuses_rankings():
    # 第 0 候选在两条腿里都排第一 → 融合分最高
    fused = _rrf([[3.0, 2.0, 1.0], [3.0, 1.0, 2.0]])
    assert max(range(3), key=lambda i: fused[i]) == 0


def _write_conventions(root: Path) -> Path:
    p = root / "conventions.json"
    p.write_text(json.dumps([
        {"id": "c1", "kind": "team_convention",
         "text": "金额必须 Decimal", "tags": ["money"], "repo": None},
        {"id": "c2", "kind": "team_convention",
         "text": "折扣率上限 20%", "tags": ["discount"], "repo": None},
    ], ensure_ascii=False), encoding="utf-8")
    return p


def test_recall_returns_conventions_for_cr(tmp_path):
    m = HybridMemory(tmp_path / "runs", _write_conventions(tmp_path))
    out = m.recall(RecallSpec(node_id="cr_agent", payload={"repo": "x"},
                              kinds=frozenset({"team_convention"})))
    assert len(out) >= 1
    assert all(e["kind"] == "team_convention" for e in out)


def test_recall_filters_by_kinds(tmp_path):
    m = HybridMemory(tmp_path / "runs", _write_conventions(tmp_path))
    out = m.recall(RecallSpec(node_id="cr", payload={},
                              kinds=frozenset({"past_review"})))
    assert out == []


def test_record_appends_past_review_and_skips_no_issues(tmp_path):
    m = HybridMemory(tmp_path / "runs", _write_conventions(tmp_path))
    m.record("t1", AgentOutput({"issues": [{"file": "a.py", "line": 1, "desc": "x"}]},
                               "", "ok"), context_id="c", commit="d")
    m.record("t2", AgentOutput({}, "", "ok"))  # 无 issues → 跳过
    m.record("t3", AgentOutput({"issues": [{"file": "a.py", "line": 1, "desc": "x"}]},
                               "", "failed"))  # 非 ok → 跳过
    lines = (tmp_path / "runs" / "memory" / "experiences.jsonl").read_text().splitlines()
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["kind"] == "past_review" and rec["context_id"] == "c"


def test_record_idempotent_on_same_context_and_commit(tmp_path):
    # A/B 反复跑同一 defect：同 (context_id, commit) 不得重复沉淀，防语料膨胀
    m = HybridMemory(tmp_path / "runs", _write_conventions(tmp_path))
    out = AgentOutput({"issues": [{"file": "a.py", "line": 1, "desc": "x"}]}, "", "ok")
    m.record("t1", out, context_id="repo:x", commit="defect-1")
    m.record("t2", out, context_id="repo:x", commit="defect-1")  # 重跑 → 跳过
    m.record("t3", out, context_id="repo:x", commit="defect-2")  # 不同 commit → 记
    lines = (tmp_path / "runs" / "memory" / "experiences.jsonl").read_text().splitlines()
    assert len(lines) == 2


def test_recall_empty_when_no_store(tmp_path):
    m = HybridMemory(tmp_path / "runs", tmp_path / "missing.json")
    assert m.recall(RecallSpec(node_id="cr", payload={},
                               kinds=frozenset({"team_convention"}))) == []


def test_loaders_skip_non_dict_entries(tmp_path):
    # I1：损坏条目（非 dict 行/元素）跳过，不得让 AttributeError 变成静默失败
    conv = tmp_path / "conventions.json"
    conv.write_text(json.dumps([
        {"id": "c1", "kind": "team_convention", "text": "金额必须 Decimal",
         "tags": ["money"], "repo": None}, 42], ensure_ascii=False),
        encoding="utf-8")
    m = HybridMemory(tmp_path / "runs", conv)
    exp = tmp_path / "runs" / "memory" / "experiences.jsonl"
    exp.parent.mkdir(parents=True)
    exp.write_text(json.dumps({"kind": "past_review", "content": "shop/a.py:1 x",
                               "source_run_id": "t", "context_id": "repo:x",
                               "commit": "d"}) + "\n123\n", encoding="utf-8")
    out = m.recall(RecallSpec(node_id="cr_agent", payload={"repo": "r"},
                              context_id="repo:x",
                              kinds=frozenset({"team_convention", "past_review"})))
    assert len(out) == 2  # 各留一条有效条目，42 与 123 被跳过


def test_recall_per_kind_quota_keeps_convention(tmp_path):
    # C2 回归（defect-5 场景）：exact 腿全 0 时约定只能靠 tie-break 进 top_k；
    # 配额保证 spec.kinds 内有候选的 kind 必有代表，A/B 结果不吃 coin flip
    conv = tmp_path / "conventions.json"
    conv.write_text(json.dumps([
        {"id": "conv-discount-cap", "kind": "team_convention",
         "text": ("本仓库约定：折扣率上限 20%（任何阶梯/促销折扣 rate ≤ 0.20），"
                  "防止大促叠加导致亏本；新增更高折扣档必须经运营审批"),
         "tags": ["discount", "rate", "promo"], "repo": None}], ensure_ascii=False),
        encoding="utf-8")
    m = HybridMemory(tmp_path / "runs", conv)
    seeds = [  # 语义相似度随序号递减的过往评审（均含 demo_repo，与 query 共享 n-gram）
        ("defect-1", "shop/stats.py", 8, "demo_repo bare except 吞异常静默返回 0"),
        ("defect-2", "shop/pricing.py", 3, "demo_repo 阶梯折扣 tier 未同步"),
        ("defect-3", "shop/pricing.py", 30, "demo_repo 退货单数量 abs 转正"),
        ("defect-4", "shop/report.py", 4, "demo_repo 报表重复实现折扣逻辑"),
        ("defect-5a", "shop/cart.py", 12, "demo_repo 购物车金额计算错误"),
        ("defect-5b", "shop/inventory.py", 7, "demo_repo 库存扣减并发问题"),
    ]
    for commit, f, line, desc in seeds:
        m.record(f"t-{commit}", AgentOutput(
            {"issues": [{"file": f, "line": line, "desc": desc}]}, "", "ok"),
            context_id="repo:demo_repo", commit=commit)
    out = m.recall(RecallSpec(
        node_id="cr_agent",
        payload={"repo": str(tmp_path / "demo_repo"), "commit": "defect-5",
                 "context_id": "repo:demo_repo"},
        context_id="repo:demo_repo",
        kinds=frozenset({"team_convention", "past_review"})))
    assert len(out) == m.top_k
    assert any(e["kind"] == "team_convention" for e in out)  # 确定性入选


def test_build_memory_dispatches(tmp_path):
    from harness.memory import NoopMemory
    assert isinstance(build_memory(tmp_path / "runs", enabled=False), NoopMemory)
    assert isinstance(build_memory(tmp_path / "runs", enabled=True,
                                   conventions_path=tmp_path / "c.json"), HybridMemory)


def _knowledge(tmp_path: Path) -> KnowledgeBase:
    corpus = tmp_path / "knowledge"
    corpus.mkdir()
    (corpus / "discount-policy.md").write_text(
        "# 折扣规范\n全场促销折扣率上限 0.20", encoding="utf-8")
    return KnowledgeBase(tmp_path / "runs", corpus, embedder=TfidfEmbedder())


def test_recall_includes_knowledge_leg(tmp_path):
    m = HybridMemory(tmp_path / "runs", _write_conventions(tmp_path),
                     knowledge=_knowledge(tmp_path))
    out = m.recall(RecallSpec(
        node_id="cr_agent", payload={"repo": "r", "commit": "defect-5"},
        kinds=frozenset({"team_convention", "past_review", "knowledge"})))
    kn = [e for e in out if e["kind"] == "knowledge"]
    assert kn and "0.20" in kn[0]["content"]      # 摘录进 content 注入 history


def test_recall_knowledge_participates_in_quota(tmp_path):
    # 配额语义随 kind 集合自动扩展：只开 knowledge 时必有其代表
    m = HybridMemory(tmp_path / "runs", _write_conventions(tmp_path),
                     knowledge=_knowledge(tmp_path))
    out = m.recall(RecallSpec(
        node_id="cr_agent", payload={"repo": "r", "commit": "defect-5"},
        kinds=frozenset({"knowledge"})))
    assert out and all(e["kind"] == "knowledge" for e in out)


def test_recall_skips_knowledge_when_kind_not_gated(tmp_path):
    kb = _knowledge(tmp_path)
    calls: list[str] = []
    kb_search = kb.search

    def _spy(q, top_k=3):
        calls.append(q)
        return kb_search(q, top_k)

    kb.search = _spy
    m = HybridMemory(tmp_path / "runs", _write_conventions(tmp_path), knowledge=kb)
    out = m.recall(RecallSpec(node_id="cr", payload={"repo": "r"},
                              kinds=frozenset({"team_convention"})))
    assert calls == []                            # kinds 未含 knowledge → 不检索
    assert all(e["kind"] != "knowledge" for e in out)


def test_recall_knowledge_failure_propagates(tmp_path):  # 矩阵 #9（memory 层）
    kb = _knowledge(tmp_path)

    def _boom(q, top_k=3):
        raise RuntimeError("knowledge down")

    kb.search = _boom
    m = HybridMemory(tmp_path / "runs", _write_conventions(tmp_path), knowledge=kb)
    with pytest.raises(RuntimeError, match="knowledge down"):
        m.recall(RecallSpec(node_id="cr", payload={"repo": "r"},
                            kinds=frozenset({"knowledge"})))
    # engine 侧由既有 memory_failed 守卫接住（test_memory_failure_never_blocks_run）


def test_build_memory_attaches_knowledge_by_default(tmp_path):
    m = build_memory(tmp_path / "runs", enabled=True,
                     conventions_path=tmp_path / "c.json")
    assert isinstance(m, HybridMemory) and m.knowledge is not None


def test_build_memory_knowledge_passthrough_and_disabled(tmp_path):
    kb = _knowledge(tmp_path)
    m = build_memory(tmp_path / "runs", enabled=True,
                     conventions_path=tmp_path / "c.json", knowledge=kb)
    assert m.knowledge is kb
    assert isinstance(build_memory(tmp_path / "runs", enabled=False), NoopMemory)
