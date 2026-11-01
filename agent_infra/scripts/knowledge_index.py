"""重建知识索引（make knowledge-index / CI）。打印模型/来源数/chunk 数。"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # 让 harness 包可从项目根 import

from harness.config import runs_root  # noqa: E402
from harness.knowledge import KnowledgeBase  # noqa: E402


def main() -> None:
    kb = KnowledgeBase(runs_root())
    n = kb.reindex()
    model = getattr(kb.embedder, "model", "tfidf")
    print(f"知识索引重建: model={model} sources={len(kb._index['sources'])} "
          f"chunks={n} -> {kb.index_path}")


if __name__ == "__main__":
    main()
