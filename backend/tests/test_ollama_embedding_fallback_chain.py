"""Tests for Ollama embedding model fallback chain."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.llm.hf_provider import (
    KeywordFallbackProvider,
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
def test_primary_fail_fallback_model_ok(mock_cls):
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
    assert provider is instances[1]
    assert mock_cls.call_count == 2


@patch("app.llm.hf_provider.OllamaEmbeddingProvider")
def test_all_fail_keyword_fallback(mock_cls):
    mock_cls.return_value.verify.side_effect = RuntimeError("down")

    provider = _build_ollama_embedding_provider(
        {
            "ollama_embedding_model": "bad-model",
            "ollama_embedding_fallback_models": ["also-bad"],
            "ollama_embedding_fallback": "keyword",
        }
    )
    assert isinstance(provider, KeywordFallbackProvider)


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
