"""Ollama LLM and embedding providers."""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx
import structlog

logger = structlog.get_logger(__name__)


class OllamaLLMProvider:
    """Chat completions via Ollama /api/chat."""

    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        temperature: float = 0.2,
        max_tokens: int = 2048,
        timeout_sec: float = 120,
        keep_alive: str = "5m",
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.model_name = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.keep_alive = keep_alive
        self._timeout = timeout_sec

    async def generate(self, messages: list[dict], **kwargs) -> str:
        payload = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": kwargs.get("temperature", self.temperature),
                "num_predict": kwargs.get("max_tokens", self.max_tokens),
            },
            "keep_alive": self.keep_alive,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(f"{self.base_url}/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "") or ""

    async def stream(self, messages: list[dict], **kwargs) -> AsyncIterator[str]:
        payload = {
            "model": kwargs.get("model", self.model),
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": kwargs.get("temperature", self.temperature),
                "num_predict": kwargs.get("max_tokens", self.max_tokens),
            },
            "keep_alive": self.keep_alive,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    content = chunk.get("message", {}).get("content")
                    if content:
                        yield content


class OllamaEmbeddingProvider:
    """Embeddings via Ollama /api/embed (0.5+) or /api/embeddings."""

    def __init__(self, base_url: str, model: str, *, timeout_sec: float = 60):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._timeout = timeout_sec

    def verify(self) -> None:
        """Sync connectivity check at startup."""
        with httpx.Client(timeout=self._timeout) as client:
            tags = client.get(f"{self.base_url}/api/tags")
            tags.raise_for_status()
            names = {m.get("name") for m in tags.json().get("models", [])}
            if self.model not in names and f"{self.model}:latest" not in names:
                # Ollama may omit :latest in tags vs pull name
                base = self.model.split(":")[0]
                if not any(n == self.model or n.startswith(f"{base}:") for n in names):
                    raise RuntimeError(
                        f"Ollama model {self.model!r} not found. "
                        f"Available: {sorted(n for n in names if n)}"
                    )
        # Probe embedding dimension
        vec = self._embed_sync("ping")
        if not vec or not isinstance(vec[0], (int, float)):
            raise RuntimeError(f"Invalid embedding vector from {self.model!r}")

    def _embed_sync(self, text: str) -> list[float]:
        with httpx.Client(timeout=self._timeout) as client:
            return self._parse_embedding(self._post_embed(client, text))

    def _post_embed(self, client: httpx.Client, text: str) -> dict:
        last_err: Exception | None = None
        for path, payload in (
            ("/api/embed", {"model": self.model, "input": text}),
            ("/api/embeddings", {"model": self.model, "prompt": text}),
        ):
            try:
                response = client.post(f"{self.base_url}{path}", json=payload)
                if response.status_code in (404, 405):
                    continue
                response.raise_for_status()
                return response.json()
            except Exception as e:
                last_err = e
        raise RuntimeError(f"Ollama embed failed for {self.model!r}: {last_err}") from last_err

    @staticmethod
    def _parse_embedding(data: dict) -> list[float]:
        if "embeddings" in data and data["embeddings"]:
            row = data["embeddings"][0]
            return [float(x) for x in row]
        if "embedding" in data and data["embedding"]:
            return [float(x) for x in data["embedding"]]
        raise RuntimeError(f"Unexpected Ollama embed response keys: {list(data.keys())}")

    async def _embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            last_err: Exception | None = None
            for path, payload in (
                ("/api/embed", {"model": self.model, "input": text}),
                ("/api/embeddings", {"model": self.model, "prompt": text}),
            ):
                try:
                    response = await client.post(f"{self.base_url}{path}", json=payload)
                    if response.status_code in (404, 405):
                        continue
                    response.raise_for_status()
                    return self._parse_embedding(response.json())
                except Exception as e:
                    last_err = e
            raise RuntimeError(f"Ollama embed failed for {self.model!r}: {last_err}") from last_err

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [await self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return await self._embed(text)


async def check_ollama(base_url: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=10) as client:
        response = await client.get(f"{base_url.rstrip('/')}/api/tags")
        response.raise_for_status()
        return response.json()
