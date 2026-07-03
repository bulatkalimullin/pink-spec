"""Tests for Kafka command/event schemas."""

import json

from app.kafka.schemas import CommandType, SessionCommand, SessionEvent


def test_session_command_round_trip():
    cmd = SessionCommand(
        type=CommandType.session_start,
        session_id="abc-123",
        payload={"idea": "test", "rules": {"spec_level": "L2"}},
    )
    restored = SessionCommand.from_json(cmd.to_json())
    assert restored.type == CommandType.session_start
    assert restored.session_id == "abc-123"
    assert restored.payload["idea"] == "test"


def test_session_event_from_envelope():
    envelope = {
        "type": "agent_started",
        "ts": "2026-01-01T00:00:00+00:00",
        "seq": 1,
        "session_id": "s1",
        "payload": {"agent_id": "researcher"},
    }
    ev = SessionEvent.from_envelope(envelope)
    assert ev.type == "agent_started"
    assert ev.seq == 1
    data = json.loads(json.dumps(ev.to_envelope()))
    assert data["payload"]["agent_id"] == "researcher"


def test_command_types():
    assert CommandType.session_cancel.value == "session.cancel"
    assert CommandType.intake_answers_ready.value == "intake.answers_ready"
