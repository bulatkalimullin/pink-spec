"""Tests for YandexGPT provider and session LLM resolver."""

from __future__ import annotations

import pytest

from app.llm.yandex_auth import YandexAuth
from app.llm.provider_resolver import merge_rules_llm_config
from app.llm.yandexgpt_provider import (
    YandexGPTLLMFallback,
    YandexGPTLLMProvider,
    _normalize_model,
    _to_yandex_messages,
    _yandex_llm_models,
)


def test_normalize_model():
    assert _normalize_model("yandexgpt-lite") == "yandexgpt-lite"
    assert _normalize_model("gpt://b1abc/yandexgpt/latest") == "yandexgpt"


def test_to_yandex_messages_maps_content_to_text():
    msgs = _to_yandex_messages(
        [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
        ]
    )
    assert msgs == [
        {"role": "system", "text": "You are helpful"},
        {"role": "user", "text": "Hello"},
    ]


def test_merge_rules_yandex_overrides():
    base = {
        "llm_provider": "ollama",
        "yandex_model": "yandexgpt-lite",
        "ollama_llm_model": "llama3.2",
        "temperature": 0.2,
    }
    rules = {
        "llm_provider": "yandexgpt",
        "yandexgpt": {"model": "yandexgpt", "temperature": 0.5, "max_tokens": 2048},
    }
    cfg = merge_rules_llm_config(base, rules)
    assert cfg["llm_provider"] == "yandexgpt"
    assert cfg["yandex_model"] == "yandexgpt"
    assert cfg["temperature"] == 0.5
    assert cfg["max_tokens"] == 2048


def test_merge_rules_ollama_overrides():
    base = {"llm_provider": "ollama", "ollama_llm_model": "llama3.2", "temperature": 0.2}
    rules = {
        "llm_provider": "ollama",
        "ollama": {"llm_model": "qwen2.5:7b", "fallback_models": ["mistral"]},
    }
    cfg = merge_rules_llm_config(base, rules)
    assert cfg["ollama_llm_model"] == "qwen2.5:7b"
    assert cfg["ollama_llm_fallbacks"] == ["mistral"]


def test_merge_rules_yandex_fallback_models():
    base = {"llm_provider": "ollama", "yandex_llm_fallbacks": []}
    rules = {
        "llm_provider": "yandexgpt",
        "yandexgpt": {"model": "yandexgpt-lite", "fallback_models": ["yandexgpt", "yandexgpt-32k"]},
    }
    cfg = merge_rules_llm_config(base, rules)
    assert cfg["yandex_llm_fallbacks"] == ["yandexgpt", "yandexgpt-32k"]


def test_yandex_llm_models_deduplicates():
    cfg = {
        "yandex_model": "yandexgpt-lite",
        "yandex_llm_fallbacks": ["yandexgpt", "yandexgpt-lite"],
    }
    assert _yandex_llm_models(cfg) == ["yandexgpt-lite", "yandexgpt"]


@pytest.mark.asyncio
async def test_yandex_llm_fallback_chain():
    auth = YandexAuth(api_key="key", folder_id="folder")
    p1 = YandexGPTLLMProvider(auth=auth, folder_id="folder", model="yandexgpt-lite")
    p2 = YandexGPTLLMProvider(auth=auth, folder_id="folder", model="yandexgpt")
    chain = YandexGPTLLMFallback([p1, p2])

    async def fail_generate(*args, **kwargs):
        raise RuntimeError("fail lite")

    async def ok_generate(*args, **kwargs):
        return "ok"

    p1.generate = fail_generate  # type: ignore[method-assign]
    p2.generate = ok_generate  # type: ignore[method-assign]

    assert await chain.generate([{"role": "user", "content": "hi"}]) == "ok"


def test_yandex_provider_requires_credentials():
    with pytest.raises(RuntimeError, match="YandexGPT auth missing"):
        YandexGPTLLMProvider(
            auth=YandexAuth(folder_id="folder"),
            folder_id="folder",
            model="yandexgpt-lite",
        )
