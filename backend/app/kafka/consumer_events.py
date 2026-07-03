"""API-side Kafka event consumer → LogBus fan-out."""

from __future__ import annotations

import asyncio
import json

import structlog

from app.kafka.config import kafka_settings
from app.services.log_bus import log_bus

logger = structlog.get_logger(__name__)


class KafkaEventConsumer:
    def __init__(self) -> None:
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
                    cfg.events_topic,
                    bootstrap_servers=cfg.bootstrap_servers,
                    group_id=cfg.api_events_group,
                    enable_auto_commit=True,
                    auto_offset_reset="latest",
                )
                await self._consumer.start()
                self._running = True
                self._task = asyncio.create_task(self._run_loop())
                logger.info(
                    "kafka_event_consumer_started",
                    topic=cfg.events_topic,
                    attempt=attempt,
                )
                return
            except Exception as e:
                last_error = e
                logger.warning(
                    "kafka_event_consumer_start_failed",
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
            f"Kafka event consumer failed after {max_attempts} attempts: {last_error}"
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
                    envelope = json.loads(msg.value.decode("utf-8"))
                    await log_bus.ingest_external(envelope)
                except Exception:
                    logger.exception("kafka_event_process_error")
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("kafka_event_consumer_loop_error")
