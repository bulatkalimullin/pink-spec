"""LLM and embedding provider protocols and factories (Ollama)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

import structlog

from app.llm.ollama_provider import OllamaEmbeddingProvider, OllamaLLMProvider

logger = structlog.get_logger(__name__)


@runtime_checkable
class LLMProvider(Protocol):
    async def generate(self, messages: list[dict], **kwargs) -> str: ...
    async def stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]: ...


@runtime_checkable
class EmbeddingProvider(Protocol):
    async def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    async def embed_query(self, text: str) -> list[float]: ...


class KeywordFallbackProvider:
    """Trivial keyword-based embeddings — last resort when Ollama embeddings fail."""

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._bag(t) for t in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._bag(text)

    @staticmethod
    def _bag(text: str) -> list[float]:
        vec = [0.0] * 256
        for ch in text.lower():
            vec[ord(ch) % 256] += 1.0
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]


class OllamaLLMFallback:
    """Try multiple Ollama models in order on failure."""

    def __init__(self, providers: list[OllamaLLMProvider], model_names: list[str]):
        self._providers = providers
        self._model_names = model_names
        self.model_name = model_names[0] if model_names else "unknown"

    async def generate(self, messages: list[dict], **kwargs) -> str:
        last_err: Exception | None = None
        for provider, model in zip(self._providers, self._model_names, strict=True):
            try:
                return await provider.generate(messages, **kwargs)
            except Exception as e:
                last_err = e
                logger.warning("ollama_llm_failed", model=model, error=str(e))
        raise RuntimeError(f"All Ollama LLM models failed. Last: {last_err}") from last_err

    async def stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        result = await self.generate(messages, **kwargs)
        for word in result.split():
            yield word + " "


def build_llm_provider(cfg: dict) -> LLMProvider:
    provider = str(cfg.get("llm_provider", "ollama")).lower()
    if provider == "yandexgpt":
        from app.llm.yandexgpt_provider import build_yandexgpt_provider

        return build_yandexgpt_provider(cfg)
    return _build_ollama_llm_provider(cfg)


def _build_ollama_llm_provider(cfg: dict) -> LLMProvider:
    import httpx

    base_url: str = cfg.get("ollama_base_url", "http://localhost:11434")
    models: list[str] = [
        m
        for m in [cfg.get("ollama_llm_model", "llama3.2"), *cfg.get("ollama_llm_fallbacks", [])]
        if m
    ]
    if not models:
        raise RuntimeError("OLLAMA_LLM_MODEL is not configured")

    temperature: float = cfg.get("temperature", 0.2)
    max_tokens: int = cfg.get("max_tokens", 2048)
    timeout_sec: float = float(cfg.get("ollama_timeout_sec", 120))
    keep_alive: str = cfg.get("ollama_keep_alive", "5m")

    with httpx.Client(timeout=10) as client:
        response = client.get(f"{base_url.rstrip('/')}/api/tags")
        response.raise_for_status()

    providers = [
        OllamaLLMProvider(
            base_url,
            model,
            temperature=temperature,
            max_tokens=max_tokens,
            timeout_sec=timeout_sec,
            keep_alive=keep_alive,
        )
        for model in models
    ]

    if len(providers) == 1:
        logger.info("llm_provider_ready", mode="ollama", model=models[0], base_url=base_url)
        return providers[0]

    logger.info(
        "llm_provider_ready",
        mode="ollama",
        model=models[0],
        fallbacks=models[1:],
        base_url=base_url,
    )
    return OllamaLLMFallback(providers, models)


def build_embedding_provider(cfg: dict) -> EmbeddingProvider:
    provider = str(cfg.get("llm_provider", "ollama")).lower()
    if provider == "yandexgpt":
        return _build_yandex_embedding_provider(cfg)
    return _build_ollama_embedding_provider(cfg)


def _build_yandex_embedding_provider(cfg: dict) -> EmbeddingProvider:
    from app.llm.yandex_embedding_provider import build_yandex_embedding_provider

    return build_yandex_embedding_provider(cfg)


def _build_ollama_embedding_provider(cfg: dict) -> EmbeddingProvider:
    base_url: str = cfg.get("ollama_base_url", "http://localhost:11434")
    model: str | None = cfg.get("ollama_embedding_model")
    fallback: str = cfg.get("ollama_embedding_fallback", "keyword")
    timeout_sec: float = float(cfg.get("ollama_timeout_sec", 120))

    if model:
        try:
            provider = OllamaEmbeddingProvider(base_url, model, timeout_sec=timeout_sec)
            provider.verify()
            logger.info("embedding_provider_ready", mode="ollama", model=model, base_url=base_url)
            return provider
        except Exception as e:
            logger.warning("ollama_embedding_failed", model=model, error=str(e))

    if fallback == "keyword":
        logger.warning("embedding_fallback_keyword")
        return KeywordFallbackProvider()

    if fallback == "none":
        raise RuntimeError(
            f"Ollama embedding model {model!r} unavailable and OLLAMA_EMBEDDING_FALLBACK=none"
        )

    raise RuntimeError(
        "No embedding provider available. Set OLLAMA_EMBEDDING_MODEL or OLLAMA_EMBEDDING_FALLBACK=keyword"
    )
