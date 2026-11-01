"""知识语料 sanity：文档集齐全 + smoke-rag 靶子（defect-5 深水信息）在文档里。"""
from pathlib import Path

CORPUS = Path(__file__).resolve().parents[2] / "knowledge"
DOCS = ["discount-policy.md", "money-decimal.md", "cr-severity.md",
        "sandbox-commands.md", "module-api.md"]


def test_corpus_docs_present_and_utf8():
    for name in DOCS:
        text = (CORPUS / name).read_text(encoding="utf-8")
        assert len(text) > 200                     # 非空壳文档


def test_discount_doc_holds_defect5_deep_water_info():
    text = (CORPUS / "discount-policy.md").read_text(encoding="utf-8")
    # smoke-rag 靶子（矩阵 #16）：promo 0.30 事故 + 0.20 上限只从文档获知
    assert "promo" in text and "0.30" in text and "0.20" in text
