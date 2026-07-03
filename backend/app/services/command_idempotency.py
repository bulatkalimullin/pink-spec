"""Kafka command idempotency — dedupe by command_id across worker restarts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import structlog

from app.db.connection import get_db

logger = structlog.get_logger(__name__)

DEFAULT_TTL_HOURS = 24


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _cutoff_iso(hours: int) -> str:
    return (datetime.now(UTC) - timedelta(hours=hours)).isoformat()


async def ensure_processed_commands_table() -> None:
    async with get_db() as db:
        await db.executescript(
            """
            CREATE TABLE IF NOT EXISTS processed_commands (
                command_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                command_type TEXT NOT NULL,
                processed_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_processed_commands_at
                ON processed_commands (processed_at);
            """
        )
        await db.commit()


async def purge_expired_commands(ttl_hours: int = DEFAULT_TTL_HOURS) -> int:
    """Delete command claims older than TTL. Returns rows removed."""
    cutoff = _cutoff_iso(ttl_hours)
    async with get_db() as db:
        cursor = await db.execute(
            "DELETE FROM processed_commands WHERE processed_at < ?",
            (cutoff,),
        )
        await db.commit()
        return cursor.rowcount or 0


async def try_claim_command(
    command_id: str,
    *,
    session_id: str,
    command_type: str,
    ttl_hours: int = DEFAULT_TTL_HOURS,
) -> bool:
    """
    Atomically claim a command for processing.

    Returns True on first claim; False if command_id was already processed
    within the retention window (Kafka redelivery / duplicate publish).
    """
    if not command_id:
        return True

    await purge_expired_commands(ttl_hours)

    async with get_db() as db:
        cursor = await db.execute(
            "INSERT OR IGNORE INTO processed_commands "
            "(command_id, session_id, command_type, processed_at) "
            "VALUES (?, ?, ?, ?)",
            (command_id, session_id, command_type, _now()),
        )
        await db.commit()
        claimed = (cursor.rowcount or 0) > 0

    if not claimed:
        logger.info(
            "command_idempotency_duplicate",
            command_id=command_id,
            session_id=session_id,
            command_type=command_type,
        )
    return claimed
