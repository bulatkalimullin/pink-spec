"""Worker-side event publisher to Kafka."""

from __future__ import annotations

from typing import Any

import structlog

from app.kafka.config import kafka_settings
from app.kafka.producer import KafkaProducerClient

logger = structlog.get_logger(__name__)


class KafkaEventPublisher:
    def __init__(self) -> None:
        self._client = KafkaProducerClient()
        self._seq_counters: dict[str, int] = {}

    async def start(self) -> None:
        await self._client.start()

    async def stop(self) -> None:
        await self._client.stop()

    def _next_seq(self, session_id: str) -> int:
        self._seq_counters[session_id] = self._seq_counters.get(session_id, 0) + 1
        return self._seq_counters[session_id]

    async def publish_envelope(self, envelope: dict[str, Any]) -> None:
        cfg = kafka_settings()
        import json

        await self._client.send(
            cfg.events_topic,
            key=envelope["session_id"],
            value=json.dumps(envelope, default=str).encode("utf-8"),
        )

    async def publish(
        self, session_id: str, event_type: str, payload: dict[str, Any], *, seq: int | None = None
    ) -> dict[str, Any]:
        from datetime import UTC, datetime

        envelope = {
            "type": event_type,
            "ts": datetime.now(UTC).isoformat(),
            "seq": seq if seq is not None else self._next_seq(session_id),
            "session_id": session_id,
            "payload": payload,
        }
        if event_type != "system_metrics":
            await self.publish_envelope(envelope)
        return envelope
