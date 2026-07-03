"""Kafka command and event schemas."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class CommandType(StrEnum):
    session_start = "session.start"
    session_restart = "session.restart"
    session_cancel = "session.cancel"
    session_control = "session.control"
    intake_answers_ready = "intake.answers_ready"
    rag_ingest = "rag.ingest"


class SessionCommand(BaseModel):
    command_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: CommandType
    session_id: str
    ts: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_json(self) -> bytes:
        return self.model_dump_json().encode("utf-8")

    @classmethod
    def from_json(cls, raw: bytes | str) -> SessionCommand:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return cls.model_validate_json(raw)


class SessionEvent(BaseModel):
    """Mirrors log_bus envelope."""

    type: str
    ts: str
    seq: int
    session_id: str
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_envelope(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_envelope(cls, envelope: dict[str, Any]) -> SessionEvent:
        return cls(
            type=envelope["type"],
            ts=envelope["ts"],
            seq=int(envelope["seq"]),
            session_id=envelope["session_id"],
            payload=envelope.get("payload") or {},
        )

    @classmethod
    def from_json(cls, raw: bytes | str) -> SessionEvent:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        data = __import__("json").loads(raw)
        return cls.from_envelope(data)
