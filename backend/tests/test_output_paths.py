"""Tests for output path slugging and resolution."""

from __future__ import annotations

import pytest

from app.services.output_paths import (
    allocate_output_slug,
    register_output_slug,
    resolve_project_name,
    slugify_project_name,
)


def test_slugify_latin():
    assert slugify_project_name("Task Tracker SaaS") == "task-tracker-saas"


def test_slugify_cyrillic():
    assert slugify_project_name("Трекер задач") == "трекер-задач"


def test_slugify_special_chars():
    assert slugify_project_name("My App!!! (v2)") == "my-app-v2"


def test_resolve_from_rules():
    name = resolve_project_name(
        "Some long idea text here",
        {"project": {"name": "task-tracker"}},
    )
    assert name == "task-tracker"


def test_resolve_fallback_from_idea():
    idea = "SaaS task tracker for remote teams with Kanban"
    name = resolve_project_name(idea, {"project": {"name": "my-project"}})
    assert "task" in name.lower() or "saas" in name.lower()


@pytest.mark.asyncio
async def test_allocate_output_slug_unique(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.output_paths.output_root", lambda: tmp_path)
    monkeypatch.setattr("app.services.output_paths._slug_to_session", {})
    monkeypatch.setattr("app.services.output_paths._slug_cache", {})

    from app.db.connection import init_db

    db_file = tmp_path / "test.db"
    monkeypatch.setenv("SQLITE_PATH", str(db_file))
    from app.config import get_settings

    get_settings.cache_clear()
    await init_db()

    slug1 = await allocate_output_slug("task-tracker")
    (tmp_path / slug1).mkdir()
    slug2 = await allocate_output_slug("task-tracker")
    assert slug1 != slug2
    assert slug2.startswith("task-tracker")


def test_get_output_slug_fallback():
    from app.services.output_paths import get_output_slug, unregister_output_slug

    sid = "uuid-session-123"
    assert get_output_slug(sid) == sid
    register_output_slug(sid, "my-project")
    assert get_output_slug(sid) == "my-project"
    unregister_output_slug(sid)
    assert get_output_slug(sid) == sid


def test_align_output_folder_moves_uuid_to_slug(tmp_path, monkeypatch):
    from app.services.output_paths import align_output_folder, register_output_slug

    monkeypatch.setattr("app.services.output_paths.output_root", lambda: tmp_path)
    session_id = "114f646a-b4a6-425e-af6a-1050b373f603"
    slug = "bluetooth-hack-python-program"
    register_output_slug(session_id, slug)

    uuid_dir = tmp_path / session_id
    docs = uuid_dir / "docs"
    docs.mkdir(parents=True)
    (docs / "scope_spec.md").write_text("# scope", encoding="utf-8")
    (tmp_path / slug).mkdir()

    resolved = align_output_folder(session_id)
    assert resolved == tmp_path / slug
    assert (resolved / "docs" / "scope_spec.md").is_file()
    assert not uuid_dir.exists()
