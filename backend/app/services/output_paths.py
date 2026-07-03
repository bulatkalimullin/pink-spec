"""Output folder naming — slug by project name, mapped from session_id."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)

DEFAULT_PROJECT_NAME = "my-project"
_slug_cache: dict[str, str] = {}
_slug_to_session: dict[str, str] = {}


def output_root() -> Path:
    return Path(get_settings().output_path)


def slugify_project_name(name: str, *, max_len: int = 60) -> str:
    """Convert human name to filesystem-safe slug."""
    text = name.strip().lower()
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text).strip("-")
    if not text:
        text = "project"
    return text[:max_len].rstrip("-")


def resolve_project_name(idea: str, rules: dict[str, Any]) -> str:
    """Pick display name from rules.project.name or idea fallback."""
    project = rules.get("project") or {}
    name = str(project.get("name") or "").strip()
    if name and name != DEFAULT_PROJECT_NAME:
        return name
    idea_text = (idea or "").strip()
    if not idea_text:
        return name or "project"
    preview = idea_text[:80].strip()
    if len(idea_text) > 80:
        preview = preview.rsplit(" ", 1)[0] if " " in preview else preview
    return preview or "project"


def register_output_slug(session_id: str, output_slug: str) -> None:
    _slug_cache[session_id] = output_slug
    _slug_to_session[output_slug] = session_id


def unregister_output_slug(session_id: str) -> None:
    slug = _slug_cache.pop(session_id, None)
    if slug and _slug_to_session.get(slug) == session_id:
        _slug_to_session.pop(slug, None)


def get_output_slug(session_id: str) -> str:
    """Resolve disk folder name; fallback to session_id for legacy sessions."""
    cached = _slug_cache.get(session_id)
    if cached:
        return cached
    db_slug = _load_slug_from_db(session_id)
    if db_slug:
        register_output_slug(session_id, db_slug)
        return db_slug
    return session_id


def _load_slug_from_db(session_id: str) -> str | None:
    """Sync DB lookup when in-memory cache is cold (e.g. Kafka worker process)."""
    import sqlite3

    from app.db.connection import DB_PATH

    if not DB_PATH.is_file():
        return None
    try:
        with sqlite3.connect(DB_PATH) as db:
            row = db.execute(
                "SELECT output_slug FROM sessions WHERE id = ? AND deleted_at IS NULL",
                (session_id,),
            ).fetchone()
    except sqlite3.Error:
        return None
    if row and row[0]:
        return str(row[0])
    return None


def align_output_folder(session_id: str) -> Path:
    """Return the directory that holds session artifacts; heal uuid→slug drift."""
    import shutil

    slug = get_output_slug(session_id)
    slug_dir = output_root() / slug
    uuid_dir = output_root() / session_id

    def file_count(path: Path) -> int:
        if not path.is_dir():
            return 0
        return sum(1 for f in path.rglob("*") if f.is_file())

    if slug != session_id and file_count(uuid_dir) > 0 and file_count(slug_dir) == 0:
        slug_dir.parent.mkdir(parents=True, exist_ok=True)
        if slug_dir.exists():
            shutil.rmtree(slug_dir)
        uuid_dir.rename(slug_dir)
        logger.info("output_folder_aligned", session_id=session_id, output_slug=slug)

    slug_dir.mkdir(parents=True, exist_ok=True)
    return slug_dir


def session_id_for_slug(output_slug: str) -> str | None:
    return _slug_to_session.get(output_slug)


async def load_all_output_slugs() -> None:
    """Populate in-memory cache from DB at startup."""
    from app.db.connection import get_db

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, output_slug FROM sessions WHERE output_slug IS NOT NULL AND deleted_at IS NULL"
        )
        rows = await cursor.fetchall()
    for row in rows:
        sid = row["id"]
        slug = row["output_slug"]
        if slug:
            register_output_slug(sid, slug)


async def allocate_output_slug(
    base_name: str,
    *,
    exclude_session_id: str | None = None,
) -> str:
    """Return unique slug, appending -2, -3 or short id on collision."""
    from app.db.connection import get_db

    base = slugify_project_name(base_name)
    candidates = [base]
    for n in range(2, 20):
        candidates.append(f"{base}-{n}")

    async with get_db() as db:
        for candidate in candidates:
            cursor = await db.execute(
                "SELECT id FROM sessions WHERE output_slug = ? AND deleted_at IS NULL",
                (candidate,),
            )
            row = await cursor.fetchone()
            if row and row["id"] != exclude_session_id:
                continue
            if candidate in _slug_to_session and _slug_to_session[candidate] != exclude_session_id:
                continue
            path = output_root() / candidate
            if path.exists() and exclude_session_id:
                owner = session_id_for_slug(candidate)
                if owner and owner != exclude_session_id:
                    continue
            elif path.exists() and not exclude_session_id:
                continue
            return candidate

    suffix = (exclude_session_id or "x")[:4]
    return f"{base}-{suffix}"
