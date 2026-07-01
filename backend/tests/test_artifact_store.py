"""Tests for disk-first artifact_store."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services import export as export_mod
from app.services.artifact_store import (
    artifact_exists,
    clear_session_output,
    init_session_output,
    is_placeholder,
    load_manifest_file,
    load_tasks_full,
    patch_manifest,
    placeholder_for,
    read_artifact,
    remove_artifact,
    save_artifact,
    save_tasks,
    slim_tasks,
)


@pytest.fixture
def output_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(export_mod, "OUTPUT_ROOT", tmp_path)
    return tmp_path


@pytest.fixture
def session_id() -> str:
    return "test-session-001"


@pytest.mark.asyncio
async def test_save_artifact_writes_disk_and_placeholder(output_root, session_id, monkeypatch):
    async def noop_save_manifest(_sid: str, _manifest: dict) -> None:
        pass

    monkeypatch.setattr(
        "app.services.artifact_store.save_manifest",
        noop_save_manifest,
    )

    init_session_output(session_id)
    placeholder = await save_artifact(session_id, "product_spec", "# Product\n\nHello")

    assert is_placeholder(placeholder)
    assert placeholder == placeholder_for(len("# Product\n\nHello"))
    assert artifact_exists(session_id, "product_spec")
    assert read_artifact(session_id, "product_spec") == "# Product\n\nHello"

    manifest = load_manifest_file(session_id)
    assert manifest["artifacts"]["product_spec"] == "docs/product_spec.md"


@pytest.mark.asyncio
async def test_remove_artifact(output_root, session_id, monkeypatch):
    async def noop_save_manifest(_sid: str, _manifest: dict) -> None:
        pass

    monkeypatch.setattr("app.services.artifact_store.save_manifest", noop_save_manifest)

    await save_artifact(session_id, "product_spec", "content")
    assert artifact_exists(session_id, "product_spec")

    remove_artifact(session_id, "product_spec")
    assert not artifact_exists(session_id, "product_spec")
    assert "product_spec" not in load_manifest_file(session_id).get("artifacts", {})


@pytest.mark.asyncio
async def test_save_tasks_rewrite_and_cache(output_root, session_id, monkeypatch):
    async def noop_save_manifest(_sid: str, _manifest: dict) -> None:
        pass

    monkeypatch.setattr("app.services.artifact_store.save_manifest", noop_save_manifest)

    task_a = {
        "id": "001",
        "phase": "01-foundation",
        "title": "Setup",
        "slug": "setup",
        "goal": "Init project",
        "context": "First task",
        "steps": ["run init"],
        "acceptance_criteria": ["works"],
        "notes": [],
        "verification": "manual",
        "depends_on": [],
        "spec_refs": [],
        "priority": "high",
        "estimated_minutes": 30,
    }
    slim = await save_tasks(session_id, [task_a])
    assert slim == [{"id": "001", "phase": "01-foundation", "title": "Setup", "slug": "setup"}]
    assert load_tasks_full(session_id) == [task_a]

    task_b = {**task_a, "id": "002", "title": "Second", "slug": "second"}
    slim2 = await save_tasks(session_id, [task_a, task_b])
    assert len(slim2) == 2
    assert load_manifest_file(session_id)["tasks"]["count"] == 2


def test_clear_session_output(output_root, session_id):
    init_session_output(session_id)
    docs = output_root / session_id / "docs"
    docs.mkdir(parents=True)
    (docs / "product_spec.md").write_text("x", encoding="utf-8")

    clear_session_output(session_id)
    assert not docs.exists()
    manifest = load_manifest_file(session_id)
    assert manifest.get("artifacts") == {}


@pytest.mark.asyncio
async def test_patch_manifest_accepts_full_manifest_dict(output_root, session_id, monkeypatch):
    async def noop_save_manifest(_sid: str, _manifest: dict) -> None:
        pass

    monkeypatch.setattr("app.services.artifact_store.save_manifest", noop_save_manifest)

    init_session_output(session_id)
    full = {
        "session_id": session_id,
        "spec_level": "L2",
        "artifacts": {"product_spec": "docs/product_spec.md"},
    }
    body = {k: v for k, v in full.items() if k != "session_id"}
    result = await patch_manifest(session_id, **body)
    assert result["session_id"] == session_id
    assert result["spec_level"] == "L2"


def test_slim_tasks():
    full = [{"id": "001", "phase": "01-x", "title": "T", "slug": "t", "goal": "g"}]
    assert slim_tasks(full) == [{"id": "001", "phase": "01-x", "title": "T", "slug": "t"}]
