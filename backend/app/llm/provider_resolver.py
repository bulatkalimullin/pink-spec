"""Merge env settings + session rules into LLM provider config."""

from __future__ import annotations

from typing import Any

from app.config import Settings, get_settings
from app.llm.hf_provider import LLMProvider, build_llm_provider


def provider_cfg_from_settings(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    return settings.provider_cfg()


def merge_rules_llm_config(base_cfg: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    """Overlay per-session rules onto env defaults."""
    cfg = dict(base_cfg)
    provider = str(rules.get("llm_provider") or cfg.get("llm_provider") or "ollama")
    cfg["llm_provider"] = provider

    if provider == "yandexgpt":
        yandex = dict(rules.get("yandexgpt") or {})
        if yandex.get("model"):
            cfg["yandex_model"] = yandex["model"]
        fallbacks = yandex.get("fallback_models")
        if fallbacks is not None:
            cfg["yandex_llm_fallbacks"] = [m for m in fallbacks if m]
        if yandex.get("embedding_doc_model"):
            cfg["yandex_embedding_doc_model"] = yandex["embedding_doc_model"]
        if yandex.get("embedding_query_model"):
            cfg["yandex_embedding_query_model"] = yandex["embedding_query_model"]
        if yandex.get("embedding_fallback"):
            cfg["yandex_embedding_fallback"] = yandex["embedding_fallback"]
        if yandex.get("embedding_fallback_doc_model"):
            cfg["yandex_embedding_fallback_doc_model"] = yandex["embedding_fallback_doc_model"]
        if yandex.get("embedding_fallback_query_model"):
            cfg["yandex_embedding_fallback_query_model"] = yandex["embedding_fallback_query_model"]
        if yandex.get("temperature") is not None:
            cfg["temperature"] = yandex["temperature"]
        if yandex.get("max_tokens") is not None:
            cfg["max_tokens"] = yandex["max_tokens"]
        if yandex.get("timeout_sec") is not None:
            cfg["yandex_timeout_sec"] = yandex["timeout_sec"]
    else:
        ollama = dict(rules.get("ollama") or {})
        if ollama.get("llm_model"):
            cfg["ollama_llm_model"] = ollama["llm_model"]
        fallbacks = ollama.get("fallback_models")
        if fallbacks is not None:
            cfg["ollama_llm_fallbacks"] = [m for m in fallbacks if m]
        if ollama.get("embedding_model"):
            cfg["ollama_embedding_model"] = ollama["embedding_model"]
        embed_fallbacks = ollama.get("embedding_fallback_models")
        if embed_fallbacks is not None:
            cfg["ollama_embedding_fallback_models"] = [m for m in embed_fallbacks if m]
        if ollama.get("embedding_fallback"):
            cfg["ollama_embedding_fallback"] = ollama["embedding_fallback"]
        if ollama.get("temperature") is not None:
            cfg["temperature"] = ollama["temperature"]
        if ollama.get("max_tokens") is not None:
            cfg["max_tokens"] = ollama["max_tokens"]
        if ollama.get("timeout_sec") is not None:
            cfg["ollama_timeout_sec"] = ollama["timeout_sec"]
        if ollama.get("keep_alive"):
            cfg["ollama_keep_alive"] = ollama["keep_alive"]

    return cfg


def build_llm_for_rules(
    rules: dict[str, Any],
    settings: Settings | None = None,
) -> LLMProvider:
    cfg = merge_rules_llm_config(provider_cfg_from_settings(settings), rules)
    return build_llm_provider(cfg)


def build_embedding_for_rules(
    rules: dict[str, Any],
    settings: Settings | None = None,
):
    from app.llm.hf_provider import build_embedding_provider

    cfg = merge_rules_llm_config(provider_cfg_from_settings(settings), rules)
    return build_embedding_provider(cfg)


def active_llm_model_name(rules: dict[str, Any], settings: Settings | None = None) -> str:
    cfg = merge_rules_llm_config(provider_cfg_from_settings(settings), rules)
    if cfg.get("llm_provider") == "yandexgpt":
        return str(cfg.get("yandex_model", "yandexgpt-lite"))
    return str(cfg.get("ollama_llm_model", "unknown"))
