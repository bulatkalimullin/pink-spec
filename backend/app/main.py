"""FastAPI application entry point."""

from __future__ import annotations

import asyncio

import structlog
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import rag, schema, sessions, system
from app.api.websocket import ws_session_handler
from app.config import get_settings
from app.db.connection import init_db
from app.services.log_bus import log_bus
from app.services.session_watchdog import watchdog
from app.services.system_monitor import system_monitor

logger = structlog.get_logger(__name__)

app = FastAPI(title="Pink Spec Agent", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router)
app.include_router(system.router)
app.include_router(rag.router)
app.include_router(schema.router)


@app.websocket("/ws/sessions/{session_id}")
async def ws_endpoint(websocket: WebSocket, session_id: str):
    await ws_session_handler(websocket, session_id)


# --- Providers (initialized at startup) ---

llm_provider = None
embedding_provider = None
settings = get_settings()


@app.on_event("startup")
async def startup():
    global llm_provider, embedding_provider, settings

    settings = get_settings()
    await init_db()

    provider_cfg = settings.provider_cfg()

    try:
        from app.llm.hf_provider import build_embedding_provider, build_llm_provider

        llm_provider = build_llm_provider(provider_cfg)
        embedding_provider = build_embedding_provider(provider_cfg)
        logger.info("providers_ready", ollama_base_url=settings.ollama_base_url)
    except Exception as e:
        logger.warning("provider_init_failed", error=str(e))
        llm_provider = _StubLLM()
        embedding_provider = _StubEmbedding()

    asyncio.create_task(log_bus.run_persist_worker())
    asyncio.create_task(system_monitor.run())
    asyncio.create_task(watchdog.run())

    logger.info("startup_complete")


@app.get("/api/v1/health")
async def health():
    info: dict = {"status": "ok", "version": "0.1.0"}
    if llm_provider is not None:
        if hasattr(llm_provider, "model_name"):
            info["llm"] = {"mode": "ollama", "model": llm_provider.model_name}
        elif hasattr(llm_provider, "model"):
            info["llm"] = {"mode": "ollama", "model": llm_provider.model}

    try:
        from app.llm.ollama_provider import check_ollama

        tags = await check_ollama(settings.ollama_base_url)
        info["ollama"] = {
            "base_url": settings.ollama_base_url,
            "llm_model": settings.ollama_llm_model,
            "embedding_model": settings.ollama_embedding_model,
            "models": [m.get("name") for m in tags.get("models", [])],
        }
    except Exception as e:
        info["ollama"] = {"base_url": settings.ollama_base_url, "error": str(e)}

    return info


class _StubLLM:
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
    async def embed_documents(self, texts):
        return [[0.1] * 64 for _ in texts]

    async def embed_query(self, text):
        return [0.1] * 64
