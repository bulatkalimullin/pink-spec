"""Simple retriever backed by ChromaDB (or BM25 keyword fallback)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)

VECTOR_PATH = Path(get_settings().vector_path)


class ChromaRetriever:
    def __init__(self, session_id: str, embedding_provider):
        import chromadb

        self._client = chromadb.PersistentClient(path=str(VECTOR_PATH))
        self._collection_name = f"pink_spec_{session_id}"
        self._embedding_provider = embedding_provider
        self._col = self._client.get_or_create_collection(self._collection_name)

    async def add_texts(self, texts: list[str], metadatas: list[dict] | None = None) -> None:
        vecs = await self._embedding_provider.embed_documents(texts)
        ids = [str(i) for i in range(self._col.count(), self._col.count() + len(texts))]
        self._col.add(
            embeddings=vecs,
            documents=texts,
            metadatas=metadatas or [{} for _ in texts],
            ids=ids,
        )

    async def retrieve(self, query: str, top_k: int = 8) -> list[dict[str, Any]]:
        vec = await self._embedding_provider.embed_query(query)
        results = self._col.query(
            query_embeddings=[vec],
            n_results=min(top_k, max(1, self._col.count())),
        )
        docs = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]
        return [{"text": doc, "distance": dist} for doc, dist in zip(docs, distances)]


class BM25Retriever:
    """Keyword fallback when ChromaDB / embeddings unavailable."""

    def __init__(self) -> None:
        self._corpus: list[str] = []
        self._bm25 = None

    async def add_texts(self, texts: list[str], metadatas: list[dict] | None = None) -> None:
        self._corpus.extend(texts)
        from rank_bm25 import BM25Okapi

        tokenized = [t.lower().split() for t in self._corpus]
        self._bm25 = BM25Okapi(tokenized)

    async def retrieve(self, query: str, top_k: int = 8) -> list[dict[str, Any]]:
        if self._bm25 is None or not self._corpus:
            return []
        tokens = query.lower().split()
        scores = self._bm25.get_scores(tokens)
        top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]
        return [{"text": self._corpus[i], "distance": 1.0 - scores[i]} for i in top_indices]
