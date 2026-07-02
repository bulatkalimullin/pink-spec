"""YandexGPT LLM provider (Foundation Models completion API)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import structlog

from app.llm.yandex_auth import YandexAuth, build_yandex_auth

logger = structlog.get_logger(__name__)

COMPLETION_URL = "https://llm.api.cloud.yandex.net/foundationModels/v1/completion"

SUPPORTED_MODELS = frozenset(
    {
        "yandexgpt-lite",
        "yandexgpt",
        "yandexgpt-32k",
        "yandexgpt-5-pro",
    }
)


def _normalize_model(model: str) -> str:
    name = (model or "yandexgpt-lite").strip()
    if name.startswith("gpt://"):
        parts = name.split("/")
        if len(parts) >= 3:
            return parts[-2]
    if name.endswith("/latest"):
        name = name.rsplit("/", 1)[0]
    return name


def _to_yandex_messages(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Map OpenAI-style messages to Yandex {role, text} format."""
    out: list[dict[str, str]] = []
    for msg in messages:
        role = str(msg.get("role", "user")).lower()
        if role not in ("system", "user", "assistant"):
            role = "user"
        text = str(msg.get("content", "")).strip()
        if not text:
            continue
        out.append({"role": role, "text": text})
    if not out:
        out.append({"role": "user", "text": "Continue."})
    return out


class YandexGPTLLMProvider:
    """Chat completions via Yandex Cloud Foundation Models API."""

    def __init__(
        self,
        *,
        auth: YandexAuth,
        folder_id: str,
        model: str = "yandexgpt-lite",
        temperature: float = 0.2,
        max_tokens: int = 4096,
        timeout_sec: float = 120,
    ) -> None:
        auth.validate()
        self._auth = auth
        self._folder_id = folder_id
        self.model = _normalize_model(model)
        self.model_name = self.model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._timeout = timeout_sec

    def _model_uri(self, model: str | None = None) -> str:
        name = _normalize_model(model or self.model)
        return f"gpt://{self._folder_id}/{name}/latest"

    async def generate(self, messages: list[dict], **kwargs) -> str:
        timeout = float(kwargs.get("timeout_sec", self._timeout))
        payload = {
            "modelUri": self._model_uri(kwargs.get("model")),
            "completionOptions": {
                "stream": False,
                "temperature": float(kwargs.get("temperature", self.temperature)),
                "maxTokens": int(kwargs.get("max_tokens", self.max_tokens)),
            },
            "messages": _to_yandex_messages(messages),
        }
        headers = await self._auth.auth_headers()
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(COMPLETION_URL, json=payload, headers=headers)
            if response.status_code >= 400:
                raise RuntimeError(
                    f"YandexGPT HTTP {response.status_code}: {response.text[:500]}"
                )
            data = response.json()
        try:
            return data["result"]["alternatives"][0]["message"]["text"]
        except (KeyError, IndexError, TypeError) as e:
            raise RuntimeError(f"Unexpected YandexGPT response: {data!r}") from e

    async def stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        result = await self.generate(messages, **kwargs)
        for word in result.split():
            yield word + " "


class YandexGPTLLMFallback:
    """Try multiple YandexGPT models in order on failure."""

    def __init__(self, providers: list[YandexGPTLLMProvider]):
        self._providers = providers
        self.model_name = providers[0].model_name if providers else "unknown"

    async def generate(self, messages: list[dict], **kwargs) -> str:
        last_err: Exception | None = None
        for provider in self._providers:
            try:
                return await provider.generate(messages, **kwargs)
            except Exception as e:
                last_err = e
                logger.warning("yandexgpt_llm_failed", model=provider.model_name, error=str(e))
        raise RuntimeError(f"All YandexGPT models failed. Last: {last_err}") from last_err

    async def stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        result = await self.generate(messages, **kwargs)
        for word in result.split():
            yield word + " "


def _yandex_llm_models(cfg: dict[str, Any]) -> list[str]:
    primary = _normalize_model(cfg.get("yandex_model", "yandexgpt-lite"))
    fallbacks = [_normalize_model(m) for m in cfg.get("yandex_llm_fallbacks", []) if m]
    models: list[str] = []
    for name in [primary, *fallbacks]:
        if name and name not in models:
            models.append(name)
    return models or ["yandexgpt-lite"]


def build_yandexgpt_provider(cfg: dict[str, Any]) -> YandexGPTLLMProvider | YandexGPTLLMFallback:
    models = _yandex_llm_models(cfg)
    for model in models:
        if model not in SUPPORTED_MODELS:
            logger.warning("yandex_unknown_model", model=model, supported=sorted(SUPPORTED_MODELS))

    auth = build_yandex_auth(cfg)
    folder_id = str(cfg.get("yandex_folder_id", ""))
    common = {
        "auth": auth,
        "folder_id": folder_id,
        "temperature": float(cfg.get("temperature", 0.2)),
        "max_tokens": int(cfg.get("max_tokens", 4096)),
        "timeout_sec": float(cfg.get("yandex_timeout_sec", cfg.get("ollama_timeout_sec", 120))),
    }
    providers = [YandexGPTLLMProvider(model=model, **common) for model in models]

    if len(providers) == 1:
        logger.info("llm_provider_ready", mode="yandexgpt", model=providers[0].model_name)
        return providers[0]

    logger.info(
        "llm_provider_ready",
        mode="yandexgpt",
        model=providers[0].model_name,
        fallbacks=[p.model_name for p in providers[1:]],
    )
    return YandexGPTLLMFallback(providers)


async def verify_yandexgpt(cfg: dict[str, Any]) -> None:
    """Light connectivity check — one minimal completion."""
    provider = build_yandexgpt_provider(cfg)
    await provider.generate([{"role": "user", "content": "ping"}], max_tokens=8)
