"""Project admin — list and soft-delete with stats preservation."""

from __future__ import annotations

from typing import Any

import structlog

from app.db.connection import get_db
from app.services.intake import clear_intake_event
from app.services.output_migration import folder_size_mb, remove_output_folder
from app.services.output_paths import get_output_slug, output_root, unregister_output_slug
from app.services.session import (
    get_session,
    list_active_sessions,
    purge_session_operational_data,
    soft_delete_session,
)
from app.services.session_control import clear_session
from app.services.session_watchdog import watchdog

logger = structlog.get_logger(__name__)

ACTIVE_BLOCK_STATUSES = frozenset({"running", "waiting_user", "starting"})


async def _has_metrics(session_id: str) -> bool:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT 1 FROM session_metrics WHERE session_id = ? LIMIT 1",
            (session_id,),
        )
        return await cursor.fetchone() is not None


async def list_projects(
    *,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    sessions, total = await list_active_sessions(limit=limit, offset=offset)
    projects: list[dict[str, Any]] = []
    for s in sessions:
        output_slug = s.get("output_slug") or get_output_slug(s["id"])
        disk_path = output_root() / output_slug
        projects.append(
            {
                "session_id": s["id"],
                "project_name": s.get("project_name") or s.get("rules", {}).get("project", {}).get("name"),
                "output_slug": output_slug,
                "status": s["status"],
                "spec_level": s["spec_level"],
                "idea_preview": (s.get("idea") or "")[:120],
                "created_at": s["created_at"],
                "updated_at": s["updated_at"],
                "disk_size_mb": folder_size_mb(disk_path),
                "has_metrics": await _has_metrics(s["id"]),
            }
        )
    return projects, total


async def get_project(session_id: str) -> dict[str, Any] | None:
    s = await get_session(session_id)
    if s is None or s.get("deleted_at"):
        return None
    output_slug = s.get("output_slug") or get_output_slug(session_id)
    disk_path = output_root() / output_slug
    return {
        "session_id": session_id,
        "project_name": s.get("project_name"),
        "output_slug": output_slug,
        "status": s["status"],
        "spec_level": s["spec_level"],
        "idea": s.get("idea"),
        "created_at": s["created_at"],
        "updated_at": s["updated_at"],
        "disk_size_mb": folder_size_mb(disk_path),
        "has_metrics": await _has_metrics(session_id),
    }


async def delete_project(session_id: str) -> dict[str, str]:
    """Remove artifacts and operational data; keep session_metrics."""
    s = await get_session(session_id)
    if s is None:
        return {"error": "not_found"}
    if s.get("deleted_at"):
        return {"error": "already_deleted"}
    if s["status"] in ACTIVE_BLOCK_STATUSES:
        return {"error": "active_session"}

    output_slug = s.get("output_slug") or get_output_slug(session_id)

    from app.services.kafka_commands import publish_cancel

    await publish_cancel(session_id)
    watchdog.unregister(session_id)
    clear_intake_event(session_id)
    clear_session(session_id)

    remove_output_folder(output_slug)
    await purge_session_operational_data(session_id)
    await soft_delete_session(session_id)
    unregister_output_slug(session_id)

    logger.info("project_deleted", session_id=session_id, output_slug=output_slug)
    return {"status": "archived", "session_id": session_id, "output_slug": output_slug}
