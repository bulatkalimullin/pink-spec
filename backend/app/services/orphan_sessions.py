"""Reconcile sessions left mid-flight after API or worker restart."""

from __future__ import annotations

from datetime import UTC, datetime

import structlog

from app.services.log_bus import log_bus
from app.services.session import get_session, is_worker_active, update_session_status

logger = structlog.get_logger(__name__)

ACTIVE_STATUSES = frozenset({"running", "waiting_user", "starting", "stuck", "paused", "queued"})


async def reconcile_orphaned_sessions() -> int:
    """Mark in-flight sessions as interrupted when worker heartbeat is stale."""
    from app.db.connection import get_db

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, status FROM sessions WHERE status IN (?, ?, ?, ?, ?, ?) AND deleted_at IS NULL",
            tuple(ACTIVE_STATUSES),
        )
        rows = await cursor.fetchall()

    count = 0
    for row in rows:
        session_id = row["id"]
        if await is_worker_active(session_id):
            continue
        await update_session_status(session_id, "interrupted")
        await log_bus.emit(
            session_id,
            "log_entry",
            {
                "level": "warn",
                "agent_id": "system",
                "message": (
                    "Сессия прервана (worker недоступен или перезапущен). "
                    "Нажмите «Перезапустить пайплайн» или создайте новую сессию."
                ),
            },
        )
        count += 1
        logger.warning("session_orphaned", session_id=session_id, previous_status=row["status"])

    if count:
        logger.info("orphan_sessions_reconciled", count=count)
    return count
