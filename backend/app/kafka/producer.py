"""Shared async Kafka producer."""

from __future__ import annotations

from typing import Any

import structlog

from app.kafka.config import kafka_settings

logger = structlog.get_logger(__name__)


class KafkaProducerClient:
    def __init__(self) -> None:
        self._producer = None
        self._started = False

    async def start(self, *, max_attempts: int = 30, delay_sec: float = 2.0) -> None:
        if self._started:
            return
        from aiokafka import AIOKafkaProducer

        cfg = kafka_settings()
        last_error: Exception | None = None
        for attempt in range(1, max_attempts + 1):
            try:
                self._producer = AIOKafkaProducer(
                    bootstrap_servers=cfg.bootstrap_servers,
                    enable_idempotence=True,
                    acks="all",
                )
                await self._producer.start()
                self._started = True
                logger.info(
                    "kafka_producer_started",
                    bootstrap=cfg.bootstrap_servers,
                    attempt=attempt,
                )
                return
            except Exception as e:
                last_error = e
                logger.warning(
                    "kafka_producer_start_failed",
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error=str(e),
                )
                if self._producer:
                    try:
                        await self._producer.stop()
                    except Exception:
                        pass
                    self._producer = None
                if attempt < max_attempts:
                    import asyncio

                    await asyncio.sleep(delay_sec)
        raise RuntimeError(
            f"Kafka producer failed after {max_attempts} attempts: {last_error}"
        ) from last_error

    async def stop(self) -> None:
        if self._producer and self._started:
            await self._producer.stop()
            self._started = False

    async def send(self, topic: str, key: str, value: bytes, headers: list | None = None) -> None:
        if not self._producer:
            raise RuntimeError("Kafka producer not started")
        await self._producer.send_and_wait(
            topic,
            value=value,
            key=key.encode("utf-8"),
            headers=headers or [],
        )

    async def health_check(self) -> dict[str, Any]:
        try:
            await self.start()
            return {"status": "ok", "bootstrap": kafka_settings().bootstrap_servers}
        except Exception as e:
            return {"status": "error", "error": str(e)}
