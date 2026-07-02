"""Tests for Yandex embedding provider."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.provider_resolver import merge_rules_llm_config
from app.llm.yandex_auth import YandexAuth
from app.llm.yandex_embedding_provider import (
    YandexEmbeddingProvider,
    YandexEmbeddingWithFallback,
    _embedding_fallback_models,
    _normalize_embedding_model,
    build_yandex_embedding_provider,
)


def test_normalize_embedding_model():
    assert _normalize_embedding_model("text-search-doc") == "text-search-doc"
    assert _normalize_embedding_model("emb://b1abc/text-search-query/latest") == "text-search-query"


def test_merge_rules_yandex_embedding_models():
    base = {
        "llm_provider": "ollama",
        "yandex_embedding_doc_model": "text-search-doc",
        "yandex_embedding_query_model": "text-search-query",
    }
    rules = {
        "llm_provider": "yandexgpt",
        "yandexgpt": {
            "embedding_doc_model": "text-search-doc",
            "embedding_query_model": "text-search-query",
        },
    }
    cfg = merge_rules_llm_config(base, rules)
    assert cfg["llm_provider"] == "yandexgpt"
    assert cfg["yandex_embedding_doc_model"] == "text-search-doc"
    assert cfg["yandex_embedding_query_model"] == "text-search-query"


@pytest.mark.asyncio
async def test_embed_query_parses_response():
    provider = YandexEmbeddingProvider(
        auth=YandexAuth(api_key="key", folder_id="folder"),
        folder_id="folder",
    )
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"embedding": [0.1, 0.2, 0.3]}

    with patch("app.llm.yandex_embedding_provider.httpx.AsyncClient") as client_cls:
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = mock_response
        client_cls.return_value = client

        with patch.object(provider._auth, "auth_headers", AsyncMock(return_value={"Authorization": "Api-Key key"})):
            vec = await provider.embed_query("hello")

    assert vec == [0.1, 0.2, 0.3]


def test_embedding_fallback_models_doc_mode():
    query_fb, doc_fb = _embedding_fallback_models({"yandex_embedding_fallback": "doc"})
    assert query_fb == "text-search-doc"
    assert doc_fb == "text-search-query"


@pytest.mark.asyncio
async def test_embedding_query_fallback_to_yandex_doc_model():
    primary = YandexEmbeddingProvider(
        auth=YandexAuth(api_key="key", folder_id="folder"),
        folder_id="folder",
    )

    async def fail_query(text: str) -> list[float]:
        raise RuntimeError("query model down")

    async def ok_doc(text: str, model: str) -> list[float]:
        assert model == "text-search-doc"
        return [0.1, 0.2]

    primary.embed_query = fail_query  # type: ignore[method-assign]
    primary.embed_one_with_model = ok_doc  # type: ignore[method-assign]

    wrapped = YandexEmbeddingWithFallback(
        primary,
        query_fallback_model="text-search-doc",
    )
    vec = await wrapped.embed_query("hello")
    assert vec == [0.1, 0.2]


def test_build_yandex_embedding_provider_verifies(monkeypatch):
    cfg = {
        "llm_provider": "yandexgpt",
        "yandex_api_key": "test-key",
        "yandex_folder_id": "folder",
        "yandex_embedding_doc_model": "text-search-doc",
        "yandex_embedding_query_model": "text-search-query",
    }

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"embedding": [0.5]}

    with patch("app.llm.yandex_embedding_provider.httpx.Client") as client_cls:
        client = MagicMock()
        client.__enter__.return_value = client
        client.post.return_value = mock_response
        client_cls.return_value = client

        provider = build_yandex_embedding_provider(cfg)

    from app.llm.yandex_embedding_provider import YandexEmbeddingWithFallback

    assert isinstance(provider, YandexEmbeddingWithFallback)
    assert provider.doc_model == "text-search-doc"
    assert provider.query_model == "text-search-query"
