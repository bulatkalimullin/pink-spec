"""Agent-worker entrypoint — consumes Kafka commands, runs AI graph."""

from __future__ import annotations

import asyncio
import os
import signal
from pathlib import Path
from typing import Any

import structlog
import uvicorn
from fastapi import FastAPI

# Must be set before other app imports that read kafka config
os.environ.setdefault("PINK_SPEC_SERVICE_ROLE", "worker")

from app.config import get_settings
from app.db.connection import init_db
from app.kafka.consumer_commands import KafkaCommandConsumer
from app.kafka.event_bridge import KafkaEventPublisher
from app.services import provider_bootstrap
from app.services.log_bus import log_bus
from app.services.session import touch_worker_heartbeat, update_session_status
from app.services.session_launcher import launch_session_graph
from app.services.session_runner import session_runner
from app.services.session_watchdog import watchdog
from app.services.system_monitor import system_monitor

logger = structlog.get_logger(__name__)

_event_publisher = KafkaEventPublisher()
_command_consumer: KafkaCommandConsumer | None = None
_shutdown_event = asyncio.Event()

health_app = FastAPI(title="Pink Spec Agent Worker", version="0.1.0")


class WorkerCommandHandler:
    async def start_session(
        self,
        session_id: str,
        *,
        idea: str,
        rules_dict: dict[str, Any],
        monitoring_cfg: dict[str, Any],
    ) -> None:
        if session_runner.is_running(session_id):
            logger.warning("session_already_running", session_id=session_id)
            return
        await update_session_status(session_id, "running")
        await touch_worker_heartbeat(session_id)
        await log_bus.emit(
            session_id,
            "worker.session_claimed",
            {"worker": "agent-worker"},
        )
        try:
            await launch_session_graph(
                session_id,
                idea=idea,
                rules_dict=rules_dict,
                monitoring_cfg=monitoring_cfg,
            )
        except RuntimeError as e:
            await update_session_status(session_id, "failed")
            await log_bus.emit(
                session_id,
                "error",
                {"message": str(e), "agent_id": "system"},
            )

    async def restart_session(
        self,
        session_id: str,
        *,
        idea: str,
        rules_dict: dict[str, Any],
        monitoring_cfg: dict[str, Any],
    ) -> None:
        await self.start_session(
            session_id,
            idea=idea,
            rules_dict=rules_dict,
            monitoring_cfg=monitoring_cfg,
        )

    async def cancel(self, session_id: str) -> None:
        session_runner.request_cancel(session_id)

    async def rag_ingest(
        self,
        session_id: str,
        *,
        temp_paths: list[str],
        sources_meta: list[dict[str, Any]],
    ) -> None:
        from app.llm.provider_resolver import build_embedding_for_rules
        from app.rag.ingest import ingest_sources
        from app.rag.retriever import BM25Retriever, ChromaRetriever
        from app.services.session import get_session

        settings = get_settings()
        session = await get_session(session_id)
        rules = (session or {}).get("rules") or {"llm_provider": settings.llm_provider}
        try:
            emb = build_embedding_for_rules(rules, settings)
            retriever = ChromaRetriever(session_id=session_id, embedding_provider=emb)
        except Exception:
            retriever = BM25Retriever()

        paths = [p for p in temp_paths if Path(p).exists()]
        if not paths:
            await log_bus.emit(
                session_id,
                "log_entry",
                {"level": "warn", "agent_id": "rag", "message": "No ingest files found"},
            )
            return
        result = await ingest_sources(paths, retriever, session_id)
        await log_bus.emit(
            session_id,
            "log_entry",
            {
                "level": "info",
                "agent_id": "rag",
                "message": f"Ingested {result.get('chunks', 0)} chunks",
                "sources_meta": sources_meta,
            },
        )
        for p in paths:
            Path(p).unlink(missing_ok=True)


async def _heartbeat_loop() -> None:
    while not _shutdown_event.is_set():
        for session_id in list(session_runner._runs.keys()):
            try:
                await touch_worker_heartbeat(session_id)
            except Exception:
                pass
        await asyncio.sleep(15)


async def run_worker() -> None:
    global _command_consumer

    settings = get_settings()
    await init_db()
    await provider_bootstrap.init_providers(settings=settings)

    log_bus.enable_worker_mode(_event_publisher)
    await _event_publisher.start()

    handler = WorkerCommandHandler()
    _command_consumer = KafkaCommandConsumer(handler)
    await _command_consumer.start()

    asyncio.create_task(log_bus.run_persist_worker())
    asyncio.create_task(system_monitor.run())
    asyncio.create_task(watchdog.run())
    asyncio.create_task(_heartbeat_loop())

    logger.info("agent_worker_started")
    await _shutdown_event.wait()


async def shutdown_worker() -> None:
    _shutdown_event.set()
    if _command_consumer:
        await _command_consumer.stop()
    await _event_publisher.stop()


@health_app.get("/health")
async def worker_health():
    settings = get_settings()
    info: dict[str, Any] = {"status": "ok", "role": "worker"}
    info["llm"] = provider_bootstrap.llm_health_info(settings)
    info["active_sessions"] = len(session_runner._runs)
    try:
        from app.llm.ollama_provider import check_ollama

        tags = await check_ollama(settings.ollama_base_url)
        info["ollama"] = {"reachable": True, "models": len(tags.get("models", []))}
    except Exception as e:
        info["ollama"] = {"reachable": False, "error": str(e)}
    return info


def main() -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def _signal_handler(*_):
        loop.create_task(shutdown_worker())

    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, _signal_handler)
        except NotImplementedError:
            pass

    async def _serve():
        config = uvicorn.Config(health_app, host="0.0.0.0", port=8001, log_level="info")
        server = uvicorn.Server(config)
        worker_task = asyncio.create_task(run_worker())
        try:
            await server.serve()
        finally:
            await shutdown_worker()
            worker_task.cancel()

    loop.run_until_complete(_serve())


if __name__ == "__main__":
    main()
