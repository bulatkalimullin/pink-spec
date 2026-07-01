"""Tests for project admin delete preserving session_metrics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import pytest_asyncio

from app.db.connection import get_db, init_db
from app.services.projects import delete_project
from app.services.session import create_session
from app.services.stats_collector import persist_session_metrics


@pytest_asyncio.fixture
async def isolated_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db_path = tmp_path / "pink.db"
    out_path = tmp_path / "output"
    out_path.mkdir()
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    monkeypatch.setenv("OUTPUT_PATH", str(out_path))
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr("app.services.export.OUTPUT_ROOT", out_path)
    monkeypatch.setattr("app.services.output_paths.output_root", lambda: out_path)
    await init_db()
    yield tmp_path
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_delete_preserves_session_metrics(isolated_db, monkeypatch):
    session_id = await create_session("L2", "Build a todo app for students", {"spec_level": "L2"})
    metrics = {
        "session_id": session_id,
        "status": "completed",
        "spec_level": "L2",
        "duration_sec": 120,
        "project_name": "todo-app",
        "scores": {"quality_score": 85.0},
    }
    await persist_session_metrics(session_id, metrics)

    result = await delete_project(session_id)
    assert result.get("status") == "archived"

    async with get_db() as db:
        cursor = await db.execute("SELECT deleted_at FROM sessions WHERE id = ?", (session_id,))
        row = await cursor.fetchone()
        assert row["deleted_at"] is not None

        cursor = await db.execute(
            "SELECT metrics_json FROM session_metrics WHERE session_id = ?",
            (session_id,),
        )
        mrow = await cursor.fetchone()
        assert mrow is not None
        saved = json.loads(mrow["metrics_json"])
        assert saved["project_name"] == "todo-app"


@pytest.mark.asyncio
async def test_delete_active_session_rejected(isolated_db):
    from app.services.session import update_session_status

    session_id = await create_session("L2", "Active project idea here", {"spec_level": "L2"})
    await update_session_status(session_id, "running")

    result = await delete_project(session_id)
    assert result.get("error") == "active_session"
