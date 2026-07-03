"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def mock_kafka_command_producer(monkeypatch, request):
    """Avoid real Kafka broker in unit tests (unless marked @pytest.mark.kafka)."""
    if request.node.get_closest_marker("kafka"):
        return

    async def _noop_publish(self, command):
        return None

    async def _noop_start(self):
        return None

    async def _noop_stop(self):
        return None

    async def _health_ok(self):
        return {"status": "ok", "bootstrap": "mock"}

    from app.kafka.command_producer import CommandProducer

    monkeypatch.setattr(CommandProducer, "publish", _noop_publish)
    monkeypatch.setattr(CommandProducer, "start", _noop_start)
    monkeypatch.setattr(CommandProducer, "stop", _noop_stop)
    monkeypatch.setattr(CommandProducer, "health_check", _health_ok)
