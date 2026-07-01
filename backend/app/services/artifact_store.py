"""Disk-first artifact storage — write-through to output/{session_id}/."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

import structlog

from app.services.export import (
    artifact_manifest_path,
    read_artifact as export_read_artifact,
    resolve_artifact_path,
    session_output_dir,
    write_artifact,
    write_manifest,
    write_task,
    write_task_index,
)
from app.services.session import save_manifest

logger = structlog.get_logger(__name__)


def placeholder_for(length: int) -> str:
    return f"<{length} chars>"


def is_placeholder(value: str) -> bool:
    return value.startswith("<") and value.endswith(" chars>")


def init_session_output(session_id: str) -> Path:
    """Create output directory and empty manifest skeleton."""
    root = session_output_dir(session_id)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        skeleton = {
            "session_id": session_id,
            "artifacts": {},
            "tasks": {"count": 0, "phases": 0},
        }
        manifest_path.write_text(
            json.dumps(skeleton, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    return root


def load_manifest_file(session_id: str) -> dict[str, Any]:
    path = session_output_dir(session_id) / "manifest.json"
    if not path.is_file():
        return {"session_id": session_id, "artifacts": {}, "tasks": {"count": 0, "phases": 0}}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_manifest_file(session_id: str, manifest: dict[str, Any]) -> None:
    write_manifest(session_id, manifest)


def _merge_manifest_updates(session_id: str, updates: dict[str, Any]) -> dict[str, Any]:
    manifest = load_manifest_file(session_id)
    for key, value in updates.items():
        if key == "session_id":
            continue
        if key == "artifacts" and isinstance(value, dict):
            artifacts = dict(manifest.get("artifacts") or {})
            artifacts.update(value)
            manifest["artifacts"] = artifacts
        elif key == "tasks" and isinstance(value, dict):
            manifest["tasks"] = {**(manifest.get("tasks") or {}), **value}
        else:
            manifest[key] = value
    manifest["session_id"] = session_id
    return manifest


async def patch_manifest(session_id: str, **updates: Any) -> dict[str, Any]:
    """Merge updates into manifest on disk and persist to SQLite."""
    manifest = await asyncio.to_thread(_merge_manifest_updates, session_id, dict(updates))
    await asyncio.to_thread(_write_manifest_file, session_id, manifest)
    try:
        await save_manifest(session_id, manifest)
    except Exception as e:
        logger.warning("manifest_db_save_failed", session_id=session_id, error=str(e))
    return manifest


def patch_manifest_disk(session_id: str, **updates: Any) -> dict[str, Any]:
    """Merge updates into manifest on disk only (sync contexts)."""
    updates = {k: v for k, v in updates.items() if k != "session_id"}
    manifest = _merge_manifest_updates(session_id, updates)
    _write_manifest_file(session_id, manifest)
    return manifest


async def save_artifact(session_id: str, artifact_type: str, content: str) -> str:
    """Write artifact to disk, update manifest, return RAM placeholder."""
    await asyncio.to_thread(write_artifact, session_id, artifact_type, content)
    await patch_manifest(
        session_id,
        artifacts={artifact_type: artifact_manifest_path(artifact_type)},
    )
    return placeholder_for(len(content))


def read_artifact(session_id: str, artifact_type: str) -> str:
    content, _ = export_read_artifact(session_id, artifact_type)
    return content


def _read_artifact_slice_sync(session_id: str, artifact_type: str, max_chars: int) -> str:
    try:
        return read_artifact(session_id, artifact_type)[:max_chars]
    except FileNotFoundError:
        return ""


async def read_artifact_slice(session_id: str, artifact_type: str, max_chars: int) -> str:
    return await asyncio.to_thread(_read_artifact_slice_sync, session_id, artifact_type, max_chars)


def _summarize_artifacts_sync(
    session_id: str,
    keys: list[str] | None,
    max_per_key: int,
    manifest: dict[str, Any] | None,
) -> str:
    m = manifest or load_manifest_file(session_id)
    artifact_keys = keys or list((m.get("artifacts") or {}).keys())
    parts: list[str] = []
    for key in artifact_keys:
        try:
            content = _read_artifact_slice_sync(session_id, key, max_per_key)
            if content:
                parts.append(f"=== {key} ===\n{content}")
        except FileNotFoundError:
            continue
    return "\n\n".join(parts)


async def summarize_artifacts(
    session_id: str,
    keys: list[str] | None = None,
    max_per_key: int = 1500,
    manifest: dict[str, Any] | None = None,
) -> str:
    """Build prompt block from on-disk artifacts."""
    return await asyncio.to_thread(
        _summarize_artifacts_sync, session_id, keys, max_per_key, manifest
    )


def artifact_exists(session_id: str, artifact_type: str) -> bool:
    return resolve_artifact_path(session_id, artifact_type) is not None


def remove_artifact(session_id: str, artifact_type: str) -> None:
    """Remove artifact file and update manifest (disk only)."""
    path = resolve_artifact_path(session_id, artifact_type)
    if path and path.is_file():
        path.unlink()
    manifest = load_manifest_file(session_id)
    artifacts = dict(manifest.get("artifacts") or {})
    artifacts.pop(artifact_type, None)
    manifest["artifacts"] = artifacts
    _write_manifest_file(session_id, manifest)


def _task_slug(task: dict[str, Any]) -> str:
    return task.get("slug", task.get("title", "task").lower().replace(" ", "-")[:40])


def slim_task(task: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": task.get("id", "000"),
        "phase": task.get("phase", "00-unknown"),
        "title": task.get("title", "Task"),
        "slug": _task_slug(task),
    }


def slim_tasks(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [slim_task(t) for t in tasks]


def _count_phases(tasks: list[dict[str, Any]]) -> int:
    return len({t.get("phase", "") for t in tasks})


def _tasks_cache_path(session_id: str) -> Path:
    return session_output_dir(session_id) / "tasks" / "_tasks.json"


def load_tasks_full(session_id: str) -> list[dict[str, Any]]:
    path = _tasks_cache_path(session_id)
    if not path.is_file():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _task_rel_path(task: dict[str, Any]) -> str:
    phase = task.get("phase", "00-unknown")
    task_id = task.get("id", "000")
    slug = _task_slug(task)
    return f"phase-{phase}/{task_id}-{slug}.md"


def _save_tasks_sync(session_id: str, tasks: list[dict[str, Any]]) -> None:
    """Write task files; incremental when only appending (same ids at start)."""
    tasks_dir = session_output_dir(session_id) / "tasks"
    old_tasks = load_tasks_full(session_id)
    old_rels = {_task_rel_path(t) for t in old_tasks}
    new_rels = {_task_rel_path(t) for t in tasks}

    if not tasks_dir.exists() or len(tasks) < len(old_tasks):
        if tasks_dir.exists():
            shutil.rmtree(tasks_dir)
        tasks_dir.mkdir(parents=True, exist_ok=True)
    else:
        tasks_dir.mkdir(parents=True, exist_ok=True)
        for rel in old_rels - new_rels:
            path = tasks_dir / rel
            if path.is_file():
                path.unlink()

    for task in tasks:
        try:
            write_task(session_id, task)
        except Exception as e:
            logger.warning("task_write_failed", task_id=task.get("id"), error=str(e))

    if tasks:
        try:
            write_task_index(session_id, tasks)
        except Exception as e:
            logger.warning("task_index_failed", error=str(e))
        _tasks_cache_path(session_id).write_text(
            json.dumps(tasks, ensure_ascii=False, indent=2), encoding="utf-8"
        )


async def save_tasks(session_id: str, tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Rewrite task files on disk (in thread) and return slim metadata for state."""
    await asyncio.to_thread(_save_tasks_sync, session_id, tasks)
    await patch_manifest(
        session_id,
        tasks={"count": len(tasks), "phases": _count_phases(tasks)},
    )
    return slim_tasks(tasks)


async def load_tasks_full_async(session_id: str) -> list[dict[str, Any]]:
    return await asyncio.to_thread(load_tasks_full, session_id)


def clear_tasks(session_id: str) -> None:
    """Remove tasks directory and reset task count in manifest."""
    tasks_dir = session_output_dir(session_id) / "tasks"
    if tasks_dir.exists():
        shutil.rmtree(tasks_dir)
    patch_manifest_disk(session_id, tasks={"count": 0, "phases": 0})


def clear_session_output(session_id: str) -> None:
    """Clear docs, tasks, and reset manifest for replan."""
    root = session_output_dir(session_id)
    for sub in ("docs", "tasks"):
        path = root / sub
        if path.exists():
            shutil.rmtree(path)
    for extra in ("gaps.md",):
        f = root / extra
        if f.is_file():
            f.unlink()
    skeleton = {
        "session_id": session_id,
        "artifacts": {},
        "tasks": {"count": 0, "phases": 0},
    }
    _write_manifest_file(session_id, skeleton)


def read_manifest_for_api(session_id: str) -> dict[str, Any] | None:
    """Load manifest from disk if present."""
    path = session_output_dir(session_id) / "manifest.json"
    if not path.is_file():
        return None
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("artifacts") or manifest.get("tasks", {}).get("count", 0) > 0:
        return manifest
    if manifest.get("session_id"):
        return manifest
    return None
