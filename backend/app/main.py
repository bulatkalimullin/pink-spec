"""FastAPI application entry point."""

from __future__ import annotations

import asyncio

import structlog
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import projects, rag, schema, sessions, stats, system
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
app.include_router(projects.router)
app.include_router(system.router)
app.include_router(stats.router)
app.include_router(rag.router)
app.include_router(schema.router)


@app.websocket("/ws/sessions/{session_id}")
async def ws_endpoint(websocket: WebSocket, session_id: str):
    await ws_session_handler(websocket, session_id)


# --- Providers (initialized at startup) ---

llm_provider = None
embedding_provider = None
settings = get_settings()

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
    max_attempts: int = _PROVIDER_INIT_ATTEMPTS,
    delay_sec: float = _PROVIDER_INIT_DELAY_SEC,
) -> bool:
    """Connect LLM + embeddings. Returns True if default LLM is ready."""
    global llm_provider, embedding_provider, settings

    settings = get_settings()
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
        hint="Configure Ollama or YandexGPT — sessions may fail until backend restarts",
    )
    return False


async def ensure_providers() -> bool:
    """Re-try providers if default LLM is on stub."""
    if not is_stub_provider(llm_provider):
        return True
    return await init_providers(max_attempts=3, delay_sec=1.0)


def llm_health_info() -> dict:
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


@app.on_event("startup")
async def startup():
    global settings

    settings = get_settings()
    await init_db()
    from app.services.orphan_sessions import reconcile_orphaned_sessions

    await reconcile_orphaned_sessions()
    await init_providers()

    from app.services.output_migration import migrate_output_folders
    from app.services.output_paths import load_all_output_slugs

    await load_all_output_slugs()
    migration_result = await migrate_output_folders()
    logger.info("output_migration_complete", **migration_result)

    asyncio.create_task(log_bus.run_persist_worker())
    asyncio.create_task(system_monitor.run())
    asyncio.create_task(watchdog.run())

    from app.services.stats_aggregator import backfill_all_sessions, needs_startup_rebuild

    if await needs_startup_rebuild():
        asyncio.create_task(backfill_all_sessions(force=False))

    logger.info("startup_complete", llm_stub=is_stub_provider(llm_provider))


@app.get("/api/v1/health")
async def health():
    info: dict = {"status": "ok", "version": "0.1.0"}

    if is_stub_provider(llm_provider):
        info["llm"] = llm_health_info()
    elif llm_provider is not None:
        info["llm"] = llm_health_info()

    info["llm_provider_default"] = settings.llm_provider
    if settings.llm_provider == "yandexgpt":
        info["yandexgpt"] = {
            "model": settings.yandex_model,
            "embedding_doc_model": settings.yandex_embedding_doc_model,
            "embedding_query_model": settings.yandex_embedding_query_model,
            "folder_id_configured": bool(settings.yandex_folder_id),
            "credentials_configured": settings.yandex_credentials_configured(),
            "auth": (
                "api_key"
                if settings.yandex_api_key
                else "passport_token"
                if settings.yandex_passport_token
                else "iam_token"
                if settings.yandex_iam_token
                else "none"
            ),
        }

    try:
        from app.llm.ollama_provider import check_ollama

        tags = await check_ollama(settings.ollama_base_url)
        info["ollama"] = {
            "base_url": settings.ollama_base_url,
            "llm_model": settings.ollama_llm_model,
            "embedding_model": settings.ollama_embedding_model,
            "models": [m.get("name") for m in tags.get("models", [])],
            "reachable": True,
        }
        if is_stub_provider(llm_provider):
            info["ollama"]["reachable_but_stub"] = True
    except Exception as e:
        info["ollama"] = {
            "base_url": settings.ollama_base_url,
            "error": str(e),
            "reachable": False,
        }

    return info
