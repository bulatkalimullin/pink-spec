"""Migrate legacy output/{uuid} folders to output/{project_slug}."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import structlog

from app.db.connection import get_db
from app.services.output_paths import (
    allocate_output_slug,
    output_root,
    register_output_slug,
    resolve_project_name,
)

logger = structlog.get_logger(__name__)


async def migrate_output_folders() -> dict[str, int]:
    """Rename UUID output dirs to project slugs for sessions missing output_slug."""
    migrated = 0
    skipped = 0
    errors = 0
    root = output_root()

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, idea, rules_json, output_slug FROM sessions WHERE deleted_at IS NULL"
        )
        rows = await cursor.fetchall()

    for row in rows:
        session_id = row["id"]
        existing_slug = row["output_slug"]
        if existing_slug:
            register_output_slug(session_id, existing_slug)
            skipped += 1
            continue

        try:
            rules = json.loads(row["rules_json"] or "{}")
            idea = row["idea"] or ""
            project_name = resolve_project_name(idea, rules)
            output_slug = await allocate_output_slug(project_name, exclude_session_id=session_id)

            uuid_dir = root / session_id
            slug_dir = root / output_slug

            if uuid_dir.is_dir() and uuid_dir != slug_dir:
                if slug_dir.exists():
                    output_slug = await allocate_output_slug(
                        f"{project_name}-{session_id[:4]}",
                        exclude_session_id=session_id,
                    )
                    slug_dir = root / output_slug
                slug_dir.parent.mkdir(parents=True, exist_ok=True)
                uuid_dir.rename(slug_dir)
                logger.info(
                    "output_folder_migrated",
                    session_id=session_id,
                    from_name=session_id,
                    to_name=output_slug,
                )
            elif not slug_dir.exists():
                slug_dir.mkdir(parents=True, exist_ok=True)

            async with get_db() as db:
                await db.execute(
                    "UPDATE sessions SET output_slug = ?, project_name = ? WHERE id = ?",
                    (output_slug, project_name, session_id),
                )
                await db.commit()

            register_output_slug(session_id, output_slug)
            migrated += 1
        except Exception:
            logger.exception("output_migration_failed", session_id=session_id)
            errors += 1

    return {"migrated": migrated, "skipped": skipped, "errors": errors}


def folder_size_mb(path: Path) -> float:
    if not path.is_dir():
        return 0.0
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return round(total / (1024 * 1024), 2)


def remove_output_folder(output_slug: str) -> None:
    path = output_root() / output_slug
    if path.is_dir():
        shutil.rmtree(path)
