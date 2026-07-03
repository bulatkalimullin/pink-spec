"""Tests for worker heartbeat and session active detection."""

import pytest

from app.services.session import is_worker_active, touch_worker_heartbeat, update_session_status


@pytest.mark.asyncio
async def test_queued_session_is_worker_active(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    from app.config import get_settings

    get_settings.cache_clear()
    import app.db.connection as conn

    conn.DB_PATH = db_path
    from app.db.connection import init_db
    from app.services.session import create_session

    await init_db()
    sid = await create_session("L2", "idea", {"spec_level": "L2"})
    await update_session_status(sid, "queued")
    assert await is_worker_active(sid) is True


@pytest.mark.asyncio
async def test_fresh_heartbeat_is_active(tmp_path, monkeypatch):
    db_path = tmp_path / "test.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_path))
    from app.config import get_settings

    get_settings.cache_clear()
    import app.db.connection as conn

    conn.DB_PATH = db_path
    from app.db.connection import init_db
    from app.services.session import create_session

    await init_db()
    sid = await create_session("L2", "idea", {"spec_level": "L2"})
    await update_session_status(sid, "running")
    await touch_worker_heartbeat(sid)
    assert await is_worker_active(sid) is True
