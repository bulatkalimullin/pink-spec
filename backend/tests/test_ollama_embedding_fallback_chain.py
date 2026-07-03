"""Tests for Ollama embedding model fallback chain."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.llm.hf_provider import (
    KeywordFallbackProvider,
    OllamaEmbeddingFallbackChain,
    _build_ollama_embedding_provider,
    _ollama_embedding_model_chain,
)


def test_embedding_model_chain_dedupes():
    cfg = {
        "ollama_embedding_model": "nomic-embed-text",
        "ollama_embedding_fallback_models": ["nomic-embed-text", "mini"],
    }
    assert _ollama_embedding_model_chain(cfg) == ["nomic-embed-text", "mini"]


@patch("app.llm.hf_provider.OllamaEmbeddingProvider")
def test_build_returns_runtime_fallback_chain(mock_cls):
    instances = [MagicMock(), MagicMock()]
    for inst in instances:
        inst.verify.return_value = None
    mock_cls.side_effect = instances

    provider = _build_ollama_embedding_provider(
        {
            "ollama_embedding_model": "primary-model",
            "ollama_embedding_fallback_models": ["secondary-model"],
            "ollama_embedding_fallback": "keyword",
        }
    )
    assert isinstance(provider, OllamaEmbeddingFallbackChain)
    assert mock_cls.call_count == 2


@patch("app.llm.hf_provider.OllamaEmbeddingProvider")
def test_startup_verify_failure_still_returns_chain(mock_cls):
    instances = [MagicMock(), MagicMock()]
    instances[0].verify.side_effect = RuntimeError("primary down")
    instances[1].verify.return_value = None
    mock_cls.side_effect = instances

    provider = _build_ollama_embedding_provider(
        {
            "ollama_embedding_model": "bad-model",
            "ollama_embedding_fallback_models": ["good-model"],
            "ollama_embedding_fallback": "none",
        }
    )
    assert isinstance(provider, OllamaEmbeddingFallbackChain)


@patch("app.llm.hf_provider.OllamaEmbeddingProvider")
def test_all_fail_keyword_only_when_no_models(mock_cls):
    provider = _build_ollama_embedding_provider(
        {
            "ollama_embedding_model": "",
            "ollama_embedding_fallback": "keyword",
        }
    )
    assert isinstance(provider, KeywordFallbackProvider)
    mock_cls.assert_not_called()


@patch("app.llm.hf_provider.OllamaEmbeddingProvider")
def test_all_fail_none_raises(mock_cls):
    mock_cls.return_value.verify.side_effect = RuntimeError("down")

    with pytest.raises(RuntimeError, match="OLLAMA_EMBEDDING_FALLBACK=none"):
        _build_ollama_embedding_provider(
            {
                "ollama_embedding_model": "bad-model",
                "ollama_embedding_fallback": "none",
            }
        )


@pytest.mark.asyncio
async def test_runtime_fallback_uses_second_model():
    primary = MagicMock()
    primary.embed_query = AsyncMock(side_effect=RuntimeError("500"))
    secondary = MagicMock()
    secondary.embed_query = AsyncMock(return_value=[0.1, 0.2])

    chain = OllamaEmbeddingFallbackChain(
        [primary, secondary],
        ["primary", "secondary"],
    )
    vec = await chain.embed_query("hello")
    assert vec == [0.1, 0.2]
    secondary.embed_query.assert_awaited_once_with("hello")


@pytest.mark.asyncio
async def test_runtime_fallback_keyword_last_resort():
    primary = MagicMock()
    primary.embed_documents = AsyncMock(side_effect=RuntimeError("500"))

    chain = OllamaEmbeddingFallbackChain(
        [primary],
        ["primary"],
        keyword_fallback=KeywordFallbackProvider(),
    )
    vecs = await chain.embed_documents(["hello"])
    assert len(vecs) == 1
    assert len(vecs[0]) == 256
