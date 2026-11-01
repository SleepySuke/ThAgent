"""检索语料与 golden 扩展钉桩（矩阵 #15）：旧 30 条零改动 + 新用例查询存在。"""
from pathlib import Path

from eval.retrieval import load_retrieval_golden

ROOT = Path(__file__).resolve().parents[2]
OLD_QUERIES = 30   # 七期基线查询数（旧条目零改动的回归锚点）


def test_corpus_file_exists_with_case_ids():
    text = (ROOT / "knowledge" / "test-cases.md").read_text(encoding="utf-8")
    for tc in ("TC-001", "TC-002", "TC-003"):
        assert tc in text
    assert "tests/test_pricing.py" in text      # 溯源路径可检索


def test_golden_old_queries_untouched_and_new_case_queries():
    golden = load_retrieval_golden()
    assert len(golden) >= OLD_QUERIES + 4
    new = [g for g in golden if g["expect"] == "test-cases.md"]
    assert len(new) >= 4 and all(g["expect"] is not None for g in new)
    # 旧 30 条首尾锚点未动（防整体重写）
    assert golden[0]["query"] == "折扣率上限是多少"
    assert golden[OLD_QUERIES - 1]["expect"] is None
