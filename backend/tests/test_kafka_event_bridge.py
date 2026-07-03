"""Tests for LogBus Kafka worker/API modes."""

import pytest

from app.kafka.event_bridge import KafkaEventPublisher
from app.services.log_bus import LogBus


class _FakePublisher:
    def __init__(self):
        self.envelopes: list[dict] = []

    async def publish_envelope(self, envelope: dict) -> None:
        self.envelopes.append(envelope)


@pytest.mark.asyncio
async def test_log_bus_worker_mode_publishes_to_kafka():
    bus = LogBus()
    fake = _FakePublisher()
    bus.enable_worker_mode(fake)  # type: ignore[arg-type]

    await bus.emit("sess-1", "log_entry", {"message": "hello"})

    assert len(fake.envelopes) == 1
    assert fake.envelopes[0]["type"] == "log_entry"
    assert fake.envelopes[0]["session_id"] == "sess-1"


@pytest.mark.asyncio
async def test_log_bus_ingest_external_broadcasts():
    bus = LogBus()
    q = bus.subscribe("sess-2")
    envelope = {
        "type": "done",
        "ts": "2026-01-01T00:00:00+00:00",
        "seq": 5,
        "session_id": "sess-2",
        "payload": {"status": "completed"},
    }
    await bus.ingest_external(envelope)
    received = q.get_nowait()
    assert received["type"] == "done"
    assert received["seq"] == 5
