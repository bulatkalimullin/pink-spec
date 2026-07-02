"""Reconcile sessions left mid-flight after backend restart."""

from __future__ import annotations

import structlog

from app.services.log_bus import log_bus
from app.services.session import update_session_status

logger = structlog.get_logger(__name__)

ACTIVE_STATUSES = frozenset({"running", "waiting_user", "starting", "stuck", "paused"})


async def reconcile_orphaned_sessions() -> int:
    """Mark in-flight sessions as interrupted when no graph task is running."""
    from app.db.connection import get_db
    from app.services.session_runner import session_runner

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, status FROM sessions WHERE status IN (?, ?, ?, ?, ?) AND deleted_at IS NULL",
            tuple(ACTIVE_STATUSES),
        )
        rows = await cursor.fetchall()

    count = 0
    for row in rows:
        session_id = row["id"]
        if session_runner.is_running(session_id):
            continue
        await update_session_status(session_id, "interrupted")
        await log_bus.emit(
            session_id,
            "log_entry",
            {
                "level": "warn",
                "agent_id": "system",
                "message": (
                    "Сессия прервана перезапуском backend. "
                    "Нажмите «Перезапустить пайплайн» или создайте новую сессию."
                ),
            },
        )
        count += 1
        logger.warning("session_orphaned", session_id=session_id, previous_status=row["status"])

    if count:
        logger.info("orphan_sessions_reconciled", count=count)
    return count
