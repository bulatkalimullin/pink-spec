"""Tests for Kafka command idempotency (P01)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest

from app.kafka.consumer_commands import KafkaCommandConsumer
from app.kafka.schemas import CommandType, SessionCommand
from app.services.command_idempotency import (
    purge_expired_commands,
    try_claim_command,
)


@pytest.fixture
def idempotency_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    from app.config import get_settings

    get_settings.cache_clear()
    import app.db.connection as conn

    conn.DB_PATH = db_path
    return db_path


async def _init_idempotency_db(db_path):
    from app.db.connection import init_db

    await init_db()


@pytest.mark.asyncio
async def test_try_claim_first_succeeds_second_duplicate(idempotency_db):
    await _init_idempotency_db(idempotency_db)
    assert await try_claim_command(
        "cmd-1",
        session_id="sess-a",
        command_type=CommandType.session_start.value,
    )
    assert not await try_claim_command(
        "cmd-1",
        session_id="sess-a",
        command_type=CommandType.session_start.value,
    )


@pytest.mark.asyncio
async def test_different_command_ids_both_claimed(idempotency_db):
    await _init_idempotency_db(idempotency_db)
    assert await try_claim_command("cmd-a", session_id="s1", command_type="session.start")
    assert await try_claim_command("cmd-b", session_id="s1", command_type="session.start")


@pytest.mark.asyncio
async def test_purge_allows_reclaim_after_ttl(idempotency_db):
    await _init_idempotency_db(idempotency_db)
    from app.db.connection import get_db

    old = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
    async with get_db() as db:
        await db.execute(
            "INSERT INTO processed_commands (command_id, session_id, command_type, processed_at) "
            "VALUES (?, ?, ?, ?)",
            ("stale-cmd", "s1", "session.start", old),
        )
        await db.commit()

    removed = await purge_expired_commands(ttl_hours=24)
    assert removed == 1
    assert await try_claim_command("stale-cmd", session_id="s1", command_type="session.start")
@pytest.mark.asyncio
async def test_kafka_redelivery_processed_once(idempotency_db):
    await _init_idempotency_db(idempotency_db)
    handler = AsyncMock()
    consumer = KafkaCommandConsumer(handler)

    cmd = SessionCommand(
        command_id="kafka-redelivery-1",
        type=CommandType.session_cancel,
        session_id="sess-y",
    )
    raw = cmd.to_json()

    class FakeMsg:
        value = raw

    async def fake_iter():
        yield FakeMsg()
        yield FakeMsg()

    async def run_two():
        async for msg in fake_iter():
            command = SessionCommand.from_json(msg.value)
            if not await try_claim_command(
                command.command_id,
                session_id=command.session_id,
                command_type=str(command.type.value),
            ):
                continue
            await consumer._dispatch(command)

    await run_two()
    handler.cancel.assert_awaited_once_with("sess-y")
