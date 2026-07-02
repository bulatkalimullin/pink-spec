"""Yandex Cloud text embeddings (Foundation Models textEmbedding API)."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import structlog

from app.llm.yandex_auth import YandexAuth, build_yandex_auth

logger = structlog.get_logger(__name__)

TEXT_EMBEDDING_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/textEmbedding"

SUPPORTED_EMBEDDING_MODELS = frozenset(
    {
        "text-search-doc",
        "text-search-query",
    }
)


def _normalize_embedding_model(model: str) -> str:
    name = (model or "text-search-doc").strip()
    if name.startswith("emb://"):
        parts = name.split("/")
        if len(parts) >= 3:
            return parts[-2]
    if name.endswith("/latest"):
        name = name.rsplit("/", 1)[0]
    return name


def _parse_embedding_response(data: dict[str, Any]) -> list[float]:
    """Support both {result: {embedding}} and flat {embedding} payloads."""
    payload = data.get("result") if isinstance(data.get("result"), dict) else data
    embedding = payload.get("embedding") if isinstance(payload, dict) else None
    if not embedding:
        raise RuntimeError(f"Unexpected Yandex embedding response: {data!r}")
    return [float(x) for x in embedding]


class YandexEmbeddingProvider:
    """Document/query embeddings via Yandex Foundation Models."""

    def __init__(
        self,
        *,
        auth: YandexAuth,
        folder_id: str,
        doc_model: str = "text-search-doc",
        query_model: str = "text-search-query",
        timeout_sec: float = 120.0,
        max_concurrency: int = 4,
    ) -> None:
        auth.validate()
        self._auth = auth
        self._folder_id = folder_id
        self.doc_model = _normalize_embedding_model(doc_model)
        self.query_model = _normalize_embedding_model(query_model)
        self.model_name = f"{self.doc_model}+{self.query_model}"
        self._timeout = timeout_sec
        self._max_concurrency = max(1, max_concurrency)

    def _model_uri(self, model: str) -> str:
        name = _normalize_embedding_model(model)
        return f"emb://{self._folder_id}/{name}/latest"

    async def _embed_one(self, text: str, model: str) -> list[float]:
        payload = {
            "modelUri": self._model_uri(model),
            "text": text,
        }
        headers = await self._auth.auth_headers()
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(TEXT_EMBEDDING_URL, json=payload, headers=headers)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Yandex embedding HTTP {response.status_code}: {response.text[:500]}"
                )
            data = response.json()
        return _parse_embedding_response(data)

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        sem = asyncio.Semaphore(self._max_concurrency)

        async def _one(text: str) -> list[float]:
            async with sem:
                return await self._embed_one(text, self.doc_model)

        return list(await asyncio.gather(*[_one(text) for text in texts]))

    async def embed_query(self, text: str) -> list[float]:
        return await self._embed_one(text, self.query_model)

    async def embed_one_with_model(self, text: str, model: str) -> list[float]:
        return await self._embed_one(text, model)

    def verify(self) -> None:
        """Sync connectivity check (startup)."""
        headers = self._auth.auth_headers_sync()
        payload = {
            "modelUri": self._model_uri(self.query_model),
            "text": "ping",
        }
        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(TEXT_EMBEDDING_URL, json=payload, headers=headers)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"Yandex embedding HTTP {response.status_code}: {response.text[:500]}"
                )
            data = response.json()
        _parse_embedding_response(data)


class YandexEmbeddingWithFallback:
    """Yandex-only runtime fallback between embedding models."""

    def __init__(
        self,
        primary: YandexEmbeddingProvider,
        *,
        query_fallback_model: str | None = None,
        doc_fallback_model: str | None = None,
    ) -> None:
        self._primary = primary
        self._query_fallback = (
            _normalize_embedding_model(query_fallback_model) if query_fallback_model else None
        )
        self._doc_fallback = (
            _normalize_embedding_model(doc_fallback_model) if doc_fallback_model else None
        )
        self.doc_model = primary.doc_model
        self.query_model = primary.query_model
        self.model_name = primary.model_name

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        try:
            return await self._primary.embed_documents(texts)
        except Exception as e:
            if not self._doc_fallback or self._doc_fallback == self._primary.doc_model:
                raise
            logger.warning(
                "yandex_embedding_doc_fallback",
                from_model=self._primary.doc_model,
                to_model=self._doc_fallback,
                error=str(e),
            )
            return await asyncio.gather(
                *[self._primary.embed_one_with_model(t, self._doc_fallback) for t in texts]
            )

    async def embed_query(self, text: str) -> list[float]:
        try:
            return await self._primary.embed_query(text)
        except Exception as e:
            if not self._query_fallback or self._query_fallback == self._primary.query_model:
                raise
            logger.warning(
                "yandex_embedding_query_fallback",
                from_model=self._primary.query_model,
                to_model=self._query_fallback,
                error=str(e),
            )
            return await self._primary.embed_one_with_model(text, self._query_fallback)


def _embedding_fallback_models(cfg: dict[str, Any]) -> tuple[str | None, str | None]:
    mode = str(cfg.get("yandex_embedding_fallback", "doc")).lower()
    if mode == "none":
        return None, None
    # doc: query→text-search-doc; doc errors→text-search-query (still Yandex)
    query_fb = _normalize_embedding_model(
        cfg.get("yandex_embedding_fallback_query_model", "text-search-doc")
    )
    doc_fb = _normalize_embedding_model(
        cfg.get("yandex_embedding_fallback_doc_model", "text-search-query")
    )
    return query_fb, doc_fb


def build_yandex_embedding_provider(cfg: dict[str, Any]) -> YandexEmbeddingProvider | YandexEmbeddingWithFallback:
    doc_model = _normalize_embedding_model(cfg.get("yandex_embedding_doc_model", "text-search-doc"))
    query_model = _normalize_embedding_model(
        cfg.get("yandex_embedding_query_model", "text-search-query")
    )
    for model in (doc_model, query_model):
        if model not in SUPPORTED_EMBEDDING_MODELS:
            logger.warning(
                "yandex_unknown_embedding_model",
                model=model,
                supported=sorted(SUPPORTED_EMBEDDING_MODELS),
            )

    provider = YandexEmbeddingProvider(
        auth=build_yandex_auth(cfg),
        folder_id=str(cfg.get("yandex_folder_id", "")),
        doc_model=doc_model,
        query_model=query_model,
        timeout_sec=float(cfg.get("yandex_timeout_sec", cfg.get("ollama_timeout_sec", 120))),
    )
    provider.verify()
    query_fb, doc_fb = _embedding_fallback_models(cfg)
    if query_fb or doc_fb:
        wrapped = YandexEmbeddingWithFallback(
            provider,
            query_fallback_model=query_fb,
            doc_fallback_model=doc_fb,
        )
        logger.info(
            "embedding_provider_ready",
            mode="yandex",
            doc_model=provider.doc_model,
            query_model=provider.query_model,
            query_fallback=query_fb,
            doc_fallback=doc_fb,
        )
        return wrapped

    logger.info(
        "embedding_provider_ready",
        mode="yandex",
        doc_model=provider.doc_model,
        query_model=provider.query_model,
    )
    return provider
