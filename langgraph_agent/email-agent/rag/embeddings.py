import os
import logging
from typing import Protocol

logger = logging.getLogger(__name__)

MAX_BATCH_SIZE = 25


class EmbeddingFunc(Protocol):
    def __call__(self, texts: list[str]) -> list[list[float]]: ...


def _dashscope_embed(texts: list[str]) -> list[list[float]]:
    from dotenv import load_dotenv
    load_dotenv()

    from dashscope import TextEmbedding

    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("DASHSCOPE_API_KEY not set")

    all_embeddings: list[list[float]] = []
    for i in range(0, len(texts), MAX_BATCH_SIZE):
        batch = texts[i : i + MAX_BATCH_SIZE]
        resp = TextEmbedding.call(
            model="text-embedding-v2",
            input=batch,
            api_key=api_key,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"Embedding API error: code={resp.status_code} msg={resp.message}"
            )
        all_embeddings.extend([item["embedding"] for item in resp.output["embeddings"]])

    return all_embeddings


def _tfidf_embed(texts: list[str]) -> list[list[float]]:
    import re
    import math
    from collections import Counter

    tokenized = [re.findall(r"[一-鿿]|[a-zA-Z]+", t.lower()) for t in texts]
    df: dict[str, int] = {}
    for tokens in tokenized:
        for word in set(tokens):
            df[word] = df.get(word, 0) + 1

    N = len(texts)
    vectors: list[list[float]] = []
    vocab = sorted(df.keys())
    for tokens in tokenized:
        tf = Counter(tokens)
        vec = [
            (tf[w] / max(len(tokens), 1))
            * math.log((N + 1) / (df[w] + 1))
            for w in vocab
        ]
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        vectors.append([v / norm for v in vec])

    return vectors


def create_embedding_function() -> EmbeddingFunc:
    try:
        _dashscope_embed(["test"])
        logger.info("Using DashScope text-embedding-v2")
        return _dashscope_embed
    except Exception:
        logger.warning("DashScope embedding unavailable, falling back to TF-IDF")
        return _tfidf_embed
