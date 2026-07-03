"""Kafka integration for API ↔ agent-worker communication."""

from app.kafka.command_producer import command_producer
from app.kafka.config import kafka_settings
from app.kafka.schemas import CommandType, SessionCommand, SessionEvent

__all__ = [
    "CommandType",
    "SessionCommand",
    "SessionEvent",
    "command_producer",
    "kafka_settings",
]
