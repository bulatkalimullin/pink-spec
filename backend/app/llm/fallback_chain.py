"""LLM fallback chain — tries Ollama models in order."""
from __future__ import annotations

import asyncio
from typing import AsyncIterator

import structlog

logger = structlog.get_logger(__name__)


class FallbackLLMChain:
    """Wraps multiple LLM providers; on failure cascades to next in chain."""

    def __init__(self, providers: list, session_id: str, model_ids: list[str]):
        self._providers = providers
        self._session_id = session_id
        self._model_ids = model_ids

    async def generate(self, messages: list[dict], **kwargs) -> str:
        from app.services.log_bus import log_bus

        last_err: Exception | None = None
        for i, (provider, model_id) in enumerate(zip(self._providers, self._model_ids)):
            try:
                result = await provider.generate(messages, **kwargs)
                if i > 0:
                    await log_bus.emit(
                        self._session_id,
                        "fallback_triggered",
                        {
                            "layer": "llm",
                            "step": "generate",
                            "from": self._model_ids[i - 1] if i > 0 else None,
                            "to": model_id,
                            "message": f"Fallback to {model_id} after failure",
                        },
                    )
                return result
            except Exception as e:
                last_err = e
                logger.warning("llm_attempt_failed", model=model_id, attempt=i, error=str(e))
                if i < len(self._providers) - 1:
                    backoff = min(2 ** i, 30)
                    await asyncio.sleep(backoff)

        raise RuntimeError(f"All LLM providers failed. Last: {last_err}") from last_err

    async def stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        result = await self.generate(messages, **kwargs)
        for chunk in result.split(" "):
            yield chunk + " "


def build_fallback_chain(cfg: dict, session_id: str) -> FallbackLLMChain:
    from app.llm.ollama_provider import OllamaLLMProvider

    model_ids = [
        m for m in [cfg.get("ollama_llm_model", "llama3.2"), *cfg.get("ollama_llm_fallbacks", [])] if m
    ]
    base_url = cfg.get("ollama_base_url", "http://localhost:11434")

    providers = []
    for model_id in model_ids:
        providers.append(
            OllamaLLMProvider(
                base_url,
                model_id,
                temperature=cfg.get("temperature", 0.2),
                max_tokens=cfg.get("max_tokens", 2048),
                timeout_sec=float(cfg.get("ollama_timeout_sec", 120)),
                keep_alive=cfg.get("ollama_keep_alive", "5m"),
            )
        )

    if not providers:
        raise RuntimeError("No Ollama LLM models configured")

    return FallbackLLMChain(providers=providers, session_id=session_id, model_ids=model_ids)
