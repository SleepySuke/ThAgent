import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def load_seed_documents() -> None:
    from rag.chroma_client import add_documents

    seed_path = Path(__file__).resolve().parent.parent / "kb_data" / "seed_docs.json"
    if not seed_path.exists():
        logger.warning("Seed document file not found: %s", seed_path)
        return

    with open(seed_path, encoding="utf-8") as f:
        docs = json.load(f)

    add_documents(docs)
    logger.info("Loaded %d seed documents into knowledge base", len(docs))
