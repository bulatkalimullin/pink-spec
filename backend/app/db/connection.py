"""SQLite connection via aiosqlite."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiosqlite

from app.config import get_settings

DB_PATH = Path(get_settings().sqlite_path)


@asynccontextmanager
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    """Yield a connection; use as: async with get_db() as db:"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db


async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                spec_level TEXT NOT NULL,
                idea TEXT NOT NULL,
                rules_json TEXT NOT NULL,
                manifest_json TEXT,
                pipeline_json TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS session_checkpoints (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                state_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE TABLE IF NOT EXISTS session_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                type TEXT NOT NULL,
                ts TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id)
            );

            CREATE INDEX IF NOT EXISTS idx_logs_session_seq
                ON session_logs (session_id, seq);

            CREATE TABLE IF NOT EXISTS open_questions (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                text TEXT NOT NULL,
                options_json TEXT,
                answer_json TEXT,
                priority TEXT NOT NULL DEFAULT 'medium',
                created_at TEXT NOT NULL,
                answered_at TEXT
            );

            CREATE TABLE IF NOT EXISTS session_metrics (
                session_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                spec_level TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                duration_sec REAL NOT NULL,
                quality_score REAL NOT NULL,
                metrics_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_session_metrics_completed
                ON session_metrics (completed_at DESC);

            CREATE TABLE IF NOT EXISTS global_stats (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                updated_at TEXT NOT NULL,
                stats_json TEXT NOT NULL
            );
        """)
        await db.commit()
        await _run_migrations(db)


async def _run_migrations(db: aiosqlite.Connection) -> None:
    """Incremental schema migrations."""
    for col, typ in (
        ("pipeline_json", "TEXT"),
        ("output_slug", "TEXT"),
        ("project_name", "TEXT"),
        ("deleted_at", "TEXT"),
    ):
        try:
            await db.execute(f"ALTER TABLE sessions ADD COLUMN {col} {typ}")
            await db.commit()
        except Exception:
            pass

    cursor = await db.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='session_metrics'"
    )
    row = await cursor.fetchone()
    if row and row[0] and "FOREIGN KEY" in row[0]:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS session_metrics_new (
                session_id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                spec_level TEXT NOT NULL,
                completed_at TEXT NOT NULL,
                duration_sec REAL NOT NULL,
                quality_score REAL NOT NULL,
                metrics_json TEXT NOT NULL
            );
            INSERT OR IGNORE INTO session_metrics_new
                SELECT session_id, status, spec_level, completed_at, duration_sec,
                       quality_score, metrics_json FROM session_metrics;
            DROP TABLE session_metrics;
            ALTER TABLE session_metrics_new RENAME TO session_metrics;
            CREATE INDEX IF NOT EXISTS idx_session_metrics_completed
                ON session_metrics (completed_at DESC);
        """)
        await db.commit()

    try:
        await db.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_output_slug "
            "ON sessions(output_slug) WHERE output_slug IS NOT NULL AND deleted_at IS NULL"
        )
        await db.commit()
    except Exception:
        pass
