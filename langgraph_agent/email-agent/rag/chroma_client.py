import logging
from pathlib import Path

from chromadb import PersistentClient
from chromadb import ClientAPI
from chromadb.api.types import EmbeddingFunction as ChromaEmbeddingFunc, Documents, Embeddings

from rag.embeddings import create_embedding_function
from utils.path_tool import get_project_root

logger = logging.getLogger(__name__)

COLLECTION_NAME = "email_kb"
_client: ClientAPI | None = None
_collection: object | None = None


class _EmbeddingFnWrapper(ChromaEmbeddingFunc):
    """将我们的 EmbeddingFunc 适配为 ChromaDB EmbeddingFunction 接口"""

    def __init__(self, fn):
        self._fn = fn

    def __call__(self, input: Documents) -> Embeddings:
        return self._fn(input)


def get_chroma_client() -> ClientAPI:
    global _client
    if _client is None:
        persist_dir = str(Path(get_project_root()) / "chroma_data")
        _client = PersistentClient(path=persist_dir)
        logger.info("ChromaDB client initialized at %s", persist_dir)
    return _client


def _get_or_create_collection():
    global _collection
    if _collection is not None:
        return _collection

    client = get_chroma_client()
    ef = create_embedding_function()
    wrapper = _EmbeddingFnWrapper(ef)

    _collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=wrapper,
        metadata={"hnsw:space": "cosine"},
    )
    return _collection


def search(query: str, n_results: int = 5) -> list[dict]:
    col = _get_or_create_collection()
    results = col.query(query_texts=[query], n_results=n_results)
    docs: list[dict] = []
    if results["ids"] and results["ids"][0]:
        ids = results["ids"][0]
        documents = results["documents"][0]
        metadatas = results["metadatas"][0] if results["metadatas"] else [{}] * len(ids)
        distances = results["distances"][0] if results["distances"] else [0] * len(ids)
        for i, doc_id in enumerate(ids):
            docs.append({
                "id": doc_id,
                "content": documents[i],
                "metadata": metadatas[i] or {},
                "score": round(1.0 - distances[i], 4),
            })
    return docs


def add_documents(docs: list[dict]) -> None:
    col = _get_or_create_collection()
    ids = [d["id"] for d in docs]
    contents = [d["content"] for d in docs]
    metadatas = [d.get("metadata", {}) for d in docs]
    col.add(ids=ids, documents=contents, metadatas=metadatas)
    logger.info("Added %d documents to ChromaDB", len(docs))


def ensure_kb_initialized() -> None:
    col = _get_or_create_collection()
    if col.count() == 0:
        logger.info("Knowledge base empty, loading seed documents...")
        from rag.document_loader import load_seed_documents
        load_seed_documents()
    else:
        logger.info("Knowledge base already has %d documents", col.count())
