"""Session CRUD and lifecycle management."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from uuid import uuid4

import structlog

from app.db.connection import get_db

logger = structlog.get_logger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def create_session(spec_level: str, idea: str, rules: dict) -> str:
    from app.services.output_paths import (
        allocate_output_slug,
        output_root,
        register_output_slug,
        resolve_project_name,
    )

    session_id = str(uuid4())
    project_name = resolve_project_name(idea, rules)
    output_slug = await allocate_output_slug(project_name)

    rules = dict(rules)
    project = dict(rules.get("project") or {})
    project["name"] = project_name
    rules["project"] = project

    async with get_db() as db:
        await db.execute(
            "INSERT INTO sessions "
            "(id, status, spec_level, idea, rules_json, output_slug, project_name, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session_id,
                "pending",
                spec_level,
                idea,
                json.dumps(rules),
                output_slug,
                project_name,
                _now(),
                _now(),
            ),
        )
        await db.commit()

    register_output_slug(session_id, output_slug)
    (output_root() / output_slug).mkdir(parents=True, exist_ok=True)

    logger.info(
        "session_created",
        session_id=session_id,
        spec_level=spec_level,
        output_slug=output_slug,
        project_name=project_name,
    )
    return session_id


async def get_session(session_id: str) -> dict | None:
    async with get_db() as db:
        cursor = await db.execute("SELECT * FROM sessions WHERE id = ?", (session_id,))
        row = await cursor.fetchone()
    if row is None:
        return None
    d = dict(row)
    d["rules"] = json.loads(d.pop("rules_json"))
    if d.get("manifest_json"):
        d["manifest"] = json.loads(d.pop("manifest_json"))
    else:
        d.pop("manifest_json", None)
        d["manifest"] = None
    if d.get("pipeline_json"):
        d["pipeline"] = json.loads(d.pop("pipeline_json"))
    else:
        d.pop("pipeline_json", None)
        d["pipeline"] = None
    return d


async def save_pipeline(session_id: str, pipeline: list, reasoning: str = "") -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE sessions SET pipeline_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps({"steps": pipeline, "reasoning": reasoning}), _now(), session_id),
        )
        await db.commit()


async def update_session_status(session_id: str, status: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE sessions SET status = ?, updated_at = ? WHERE id = ?",
            (status, _now(), session_id),
        )
        await db.commit()


async def touch_worker_heartbeat(session_id: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE sessions SET worker_heartbeat_at = ?, updated_at = ? WHERE id = ?",
            (_now(), _now(), session_id),
        )
        await db.commit()


async def is_worker_active(session_id: str, max_age_sec: int = 90) -> bool:
    """True if session is queued or worker heartbeat is fresh."""
    session = await get_session(session_id)
    if not session:
        return False
    status = session.get("status", "")
    if status == "queued":
        return True
    if status not in ("running", "waiting_user", "paused", "stuck"):
        return False
    hb = session.get("worker_heartbeat_at")
    if not hb:
        return False
    try:
        from datetime import datetime

        ts = datetime.fromisoformat(hb.replace("Z", "+00:00"))
        age = (datetime.now(UTC) - ts).total_seconds()
        return age <= max_age_sec
    except Exception:
        return False


async def save_manifest(session_id: str, manifest: dict) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE sessions SET manifest_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(manifest), _now(), session_id),
        )
        await db.commit()


async def save_checkpoint(session_id: str, agent_id: str, state: dict) -> str:
    checkpoint_id = str(uuid4())
    async with get_db() as db:
        await db.execute(
            "INSERT INTO session_checkpoints (id, session_id, agent_id, state_json, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (checkpoint_id, session_id, agent_id, json.dumps(state, default=str), _now()),
        )
        await db.commit()
    return checkpoint_id


async def get_latest_checkpoint(session_id: str) -> dict | None:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM session_checkpoints WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    d = dict(row)
    d["state"] = json.loads(d.pop("state_json"))
    return d


async def save_question(
    session_id: str, question_id: str, text: str, options: list, priority: str
) -> None:
    async with get_db() as db:
        await db.execute(
            "INSERT OR IGNORE INTO open_questions (id, session_id, text, options_json, priority, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (question_id, session_id, text, json.dumps(options), priority, _now()),
        )
        await db.commit()


async def answer_question(session_id: str, question_id: str, answer) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE open_questions SET answer_json = ?, answered_at = ? WHERE id = ? AND session_id = ?",
            (json.dumps(answer), _now(), question_id, session_id),
        )
        await db.commit()


async def list_active_sessions(
    *,
    limit: int = 100,
    offset: int = 0,
    include_archived: bool = False,
) -> tuple[list[dict], int]:
    async with get_db() as db:
        where = "" if include_archived else "WHERE deleted_at IS NULL"
        count_cursor = await db.execute(f"SELECT COUNT(*) FROM sessions {where}")
        total = (await count_cursor.fetchone())[0]
        cursor = await db.execute(
            f"SELECT * FROM sessions {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        )
        rows = await cursor.fetchall()

    sessions = []
    for row in rows:
        d = dict(row)
        d["rules"] = json.loads(d.pop("rules_json"))
        d.pop("manifest_json", None)
        d.pop("pipeline_json", None)
        sessions.append(d)
    return sessions, total


async def soft_delete_session(session_id: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE sessions SET status = 'archived', deleted_at = ?, updated_at = ? WHERE id = ?",
            (_now(), _now(), session_id),
        )
        await db.commit()


async def purge_session_operational_data(session_id: str) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM session_logs WHERE session_id = ?", (session_id,))
        await db.execute("DELETE FROM session_checkpoints WHERE session_id = ?", (session_id,))
        await db.execute("DELETE FROM open_questions WHERE session_id = ?", (session_id,))
        await db.commit()


async def get_open_questions(session_id: str) -> list[dict]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM open_questions WHERE session_id = ? AND answered_at IS NULL ORDER BY created_at",
            (session_id,),
        )
        rows = await cursor.fetchall()
    return [
        {
            **{k: v for k, v in dict(r).items() if k not in ("options_json",)},
            "options": json.loads(r["options_json"] or "[]"),
        }
        for r in rows
    ]
