"""FastAPI application entry point — API gateway (no in-process agent graph)."""

from __future__ import annotations

import asyncio
import os

import structlog
from fastapi import FastAPI, WebSocket
from fastapi.middleware.cors import CORSMiddleware

os.environ.setdefault("PINK_SPEC_SERVICE_ROLE", "api")

from app.api.routes import projects, rag, schema, sessions, stats, system
from app.api.websocket import ws_session_handler
from app.config import get_settings
from app.db.connection import init_db
from app.kafka.command_producer import command_producer
from app.kafka.consumer_events import KafkaEventConsumer
from app.services.log_bus import log_bus

logger = structlog.get_logger(__name__)

app = FastAPI(title="Pink Spec Agent", version="0.2.0")

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

_kafka_event_consumer = KafkaEventConsumer()
settings = get_settings()


@app.websocket("/ws/sessions/{session_id}")
async def ws_endpoint(websocket: WebSocket, session_id: str):
    await ws_session_handler(websocket, session_id)


@app.on_event("startup")
async def startup():
    global settings

    settings = get_settings()
    await init_db()
    from app.services.orphan_sessions import reconcile_orphaned_sessions

    await reconcile_orphaned_sessions()

    from app.services.output_migration import migrate_output_folders
    from app.services.output_paths import load_all_output_slugs

    await load_all_output_slugs()
    migration_result = await migrate_output_folders()
    logger.info("output_migration_complete", **migration_result)

    await command_producer.start()
    await _kafka_event_consumer.start()
    asyncio.create_task(log_bus.run_persist_worker())

    from app.services.stats_aggregator import backfill_all_sessions, needs_startup_rebuild

    if await needs_startup_rebuild():
        asyncio.create_task(backfill_all_sessions(force=False))

    logger.info("api_startup_complete", mode="kafka")


@app.on_event("shutdown")
async def shutdown():
    await _kafka_event_consumer.stop()
    await command_producer.stop()


@app.get("/api/v1/health")
async def health():
    info: dict = {"status": "ok", "version": "0.2.0", "mode": "kafka"}
    info["kafka"] = await command_producer.health_check()
    info["llm_provider_default"] = settings.llm_provider
    info["note"] = "LLM inference runs in agent-worker service"
    return info
