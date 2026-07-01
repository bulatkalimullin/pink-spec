"""SQLite connection via aiosqlite."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

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
        """)
        await db.commit()
        # Migration: add pipeline_json column if missing
        try:
            await db.execute("ALTER TABLE sessions ADD COLUMN pipeline_json TEXT")
            await db.commit()
        except Exception:
            pass
