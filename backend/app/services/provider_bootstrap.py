"""LLM provider initialization shared by API health checks and agent-worker."""

from __future__ import annotations

import asyncio

import structlog

from app.config import Settings, get_settings

logger = structlog.get_logger(__name__)

llm_provider = None
embedding_provider = None

_PROVIDER_INIT_ATTEMPTS = 10
_PROVIDER_INIT_DELAY_SEC = 3.0


class _StubLLM:
    is_stub = True

    async def generate(self, messages, **kwargs):
        idea = ""
        for m in messages:
            if m.get("role") == "user":
                idea = m.get("content", "")[:100]
                break
        return f"# Stub Output\n\nGenerated for: {idea}\n\n[Stub: start Ollama and pull models]"

    async def stream(self, messages, **kwargs):
        result = await self.generate(messages, **kwargs)
        for word in result.split():
            yield word + " "


class _StubEmbedding:
    is_stub = True

    async def embed_documents(self, texts):
        return [[0.1] * 64 for _ in texts]

    async def embed_query(self, text):
        return [0.1] * 64


def is_stub_provider(provider: object | None) -> bool:
    return provider is None or getattr(provider, "is_stub", False)


def _use_stub_providers() -> None:
    global llm_provider, embedding_provider
    llm_provider = _StubLLM()
    embedding_provider = _StubEmbedding()


async def init_providers(
    *,
    settings: Settings | None = None,
    max_attempts: int = _PROVIDER_INIT_ATTEMPTS,
    delay_sec: float = _PROVIDER_INIT_DELAY_SEC,
) -> bool:
    """Connect LLM + embeddings. Returns True if default LLM is ready."""
    global llm_provider, embedding_provider

    settings = settings or get_settings()
    provider_cfg = settings.provider_cfg()

    from app.llm.hf_provider import build_embedding_provider, build_llm_provider

    llm_ready = False
    for attempt in range(1, max_attempts + 1):
        try:
            if settings.llm_provider == "yandexgpt":
                if settings.yandex_credentials_configured():
                    llm_provider = build_llm_provider(provider_cfg)
                    llm_ready = True
                else:
                    logger.warning("yandexgpt_not_configured", attempt=attempt)
            else:
                llm_provider = build_llm_provider(provider_cfg)
                llm_ready = True

            embedding_provider = build_embedding_provider(provider_cfg)
            if llm_ready:
                logger.info(
                    "providers_ready",
                    attempt=attempt,
                    llm_provider=settings.llm_provider,
                    ollama_base_url=settings.ollama_base_url,
                )
                return True
        except Exception as e:
            logger.warning(
                "provider_init_failed",
                attempt=attempt,
                max_attempts=max_attempts,
                error=str(e),
            )
            if attempt < max_attempts:
                await asyncio.sleep(delay_sec)

    _use_stub_providers()
    logger.error(
        "providers_stub_active",
        hint="Configure Ollama or YandexGPT — sessions may fail until worker restarts",
    )
    return False


async def ensure_providers(settings: Settings | None = None) -> bool:
    if not is_stub_provider(llm_provider):
        return True
    return await init_providers(settings=settings, max_attempts=3, delay_sec=1.0)


def llm_health_info(settings: Settings | None = None) -> dict:
    settings = settings or get_settings()
    if is_stub_provider(llm_provider):
        return {
            "mode": "stub",
            "warning": "LLM provider unavailable at init — check Ollama or YandexGPT config",
        }
    if llm_provider is None:
        return {"mode": "none"}
    mode = getattr(llm_provider, "model_name", None) and (
        "yandexgpt" if "yandex" in type(llm_provider).__name__.lower() else "ollama"
    )
    if hasattr(llm_provider, "model_name"):
        return {"mode": mode or settings.llm_provider, "model": llm_provider.model_name}
    if hasattr(llm_provider, "model"):
        return {"mode": mode or settings.llm_provider, "model": llm_provider.model}
    return {"mode": settings.llm_provider}
