"""Worker-side Kafka command consumer."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from app.kafka.config import kafka_settings
from app.kafka.schemas import CommandType, SessionCommand
from app.services.command_idempotency import try_claim_command
from app.services.intake import notify_intake_resolved
from app.services.session_control import enqueue

logger = structlog.get_logger(__name__)


class KafkaCommandConsumer:
    def __init__(self, handler) -> None:
        self._handler = handler
        self._consumer = None
        self._task: asyncio.Task | None = None
        self._running = False

    async def start(self, *, max_attempts: int = 30, delay_sec: float = 2.0) -> None:
        if self._running:
            return
        from aiokafka import AIOKafkaConsumer

        cfg = kafka_settings()
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                self._consumer = AIOKafkaConsumer(
                    cfg.commands_topic,
                    bootstrap_servers=cfg.bootstrap_servers,
                    group_id=cfg.worker_group,
                    enable_auto_commit=True,
                    auto_offset_reset="earliest",
                )
                await self._consumer.start()
                self._running = True
                self._task = asyncio.create_task(self._run_loop())
                logger.info(
                    "kafka_command_consumer_started",
                    topic=cfg.commands_topic,
                    attempt=attempt,
                )
                return
            except Exception as e:
                last_error = e
                logger.warning(
                    "kafka_command_consumer_start_failed",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error=str(e),
                )
                if self._consumer:
                    try:
                        await self._consumer.stop()
                    except Exception:
                        pass
                    self._consumer = None
                if attempt < max_attempts:
                    await asyncio.sleep(delay_sec)
        raise RuntimeError(
            f"Kafka command consumer failed after {max_attempts} attempts: {last_error}"
        ) from last_error

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._consumer:
            await self._consumer.stop()

    async def _run_loop(self) -> None:
        assert self._consumer is not None
        try:
            async for msg in self._consumer:
                if not self._running:
                    break
                try:
                    command = SessionCommand.from_json(msg.value)
                    if not await try_claim_command(
                        command.command_id,
                        session_id=command.session_id,
                        command_type=str(command.type.value),
                    ):
                        continue
                    await self._dispatch(command)
                except Exception:
                    logger.exception("kafka_command_process_error", raw=msg.value[:200])
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("kafka_command_consumer_loop_error")

    async def _dispatch(self, command: SessionCommand) -> None:
        ctype = command.type
        session_id = command.session_id
        payload = command.payload

        if ctype == CommandType.intake_answers_ready:
            notify_intake_resolved(session_id)
            return

        if ctype == CommandType.session_cancel:
            await self._handler.cancel(session_id)
            return

        if ctype == CommandType.session_control:
            action = payload.get("action")
            if action:
                enqueue(session_id, payload)
            if action in ("cancel", "force_export"):
                await self._handler.cancel(session_id)
            return

        if ctype == CommandType.session_start:
            await self._handler.start_session(
                session_id,
                idea=payload["idea"],
                rules_dict=payload["rules"],
                monitoring_cfg=payload.get("monitoring") or {},
            )
            return

        if ctype == CommandType.session_restart:
            await self._handler.restart_session(
                session_id,
                idea=payload["idea"],
                rules_dict=payload["rules"],
                monitoring_cfg=payload.get("monitoring") or {},
            )
            return

        if ctype == CommandType.rag_ingest:
            await self._handler.rag_ingest(
                session_id,
                temp_paths=payload.get("temp_paths") or [],
                sources_meta=payload.get("sources_meta") or [],
            )
            return

        logger.warning("unknown_command_type", type=str(ctype))
