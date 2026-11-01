"""检索 Benchmark 的指标数学与 golden 形状（不烧 API，用 fabricated 命中）。"""
from pathlib import Path

from eval.retrieval import load_retrieval_golden, score_all, score_query


def _hit(path, score=0.9):
    return {"path": path, "score": score, "snippet": "s"}


def test_score_query_hit_ranks():
    r = score_query({"query": "q", "expect": "a.md"},
                    [_hit("b.md"), _hit("a.md")], 0.30)
    assert r["hit1"] is False and r["hit3"] is True
    assert r["rr"] == 0.5


def test_should_miss_below_threshold_counts_correct():
    ok = score_query({"query": "q", "expect": None}, [_hit("x.md", 0.10)], 0.30)
    assert ok["miss_ok"] is True
    bad = score_query({"query": "q", "expect": None}, [_hit("x.md", 0.80)], 0.30)
    assert bad["miss_ok"] is False   # 高分命中 = 检索误报（矩阵 #11）


def test_score_all_aggregates_and_misses_in_denominator():
    golden = [{"query": "a", "expect": "a.md"},
              {"query": "b", "expect": "b.md"},
              {"query": "c", "expect": None}]
    results = [[_hit("a.md")], [_hit("z.md", 0.1)], [_hit("y.md", 0.1)]]
    m = score_all(golden, results, 0.30)
    assert m["hit1"] == 0.5 and m["hit3"] == 0.5 and m["mrr"] == 0.5
    assert m["accuracy"] == 2 / 3  # 1 命中 + 1 正确拒绝，should-miss 计入分母


def test_golden_shape_and_corpus_targets_exist():
    golden = load_retrieval_golden()
    assert len(golden) >= 30
    assert sum(1 for g in golden if g["expect"] is None) >= 5   # should-miss 起步量
    corpus = Path(__file__).resolve().parents[2] / "knowledge"
    for g in golden:
        assert g["query"].strip()                       # 查询非空白（矩阵 #7 的镜像）
        if g["expect"]:
            assert (corpus / g["expect"]).exists(), g["expect"]
