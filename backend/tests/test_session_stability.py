"""Tests for session stability refactor (phase 1)."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.agent.supervisor import _route_next, _step_done
from app.services.session_watchdog import SessionState


def test_step_done_treats_failed_as_incomplete():
    assert _step_done({"architect": "failed"}, "architect") is False
    assert _step_done({"architect": "done"}, "architect") is True
    assert _step_done({}, "architect") is False


def test_route_next_retries_failed_step():
    state = {
        "spec_level": "L2",
        "pipeline": [
            {
                "id": "product_analyst",
                "executor": "builtin:product_analyst",
                "executor_agent": "product_analyst",
            },
            {
                "id": "architect",
                "executor": "builtin:architect",
                "executor_agent": "architect",
            },
        ],
        "agent_outputs": {"product_analyst": "failed"},
    }
    assert _route_next(state) == "product_analyst"


def test_watchdog_stuck_persists_after_detection():
    state = SessionState(session_id="s1", stuck_detection_sec=1, last_progress_at=time.time() - 10)
    assert state.is_stuck() is True
    state.status = "stuck"
    state.stuck_detected_at = time.time() - 5
    assert state.is_stuck() is True
    assert state.stuck_since_sec() is not None


@pytest.mark.asyncio
async def test_save_tasks_runs_in_thread(monkeypatch, tmp_path):
    from app.services import export as export_mod
    from app.services.artifact_store import save_tasks

    monkeypatch.setattr(export_mod, "OUTPUT_ROOT", tmp_path)

    async def noop_save_manifest(_sid: str, _manifest: dict) -> None:
        pass

    monkeypatch.setattr("app.services.artifact_store.save_manifest", noop_save_manifest)

    loop_blocked = {"value": False}

    async def block_loop():
        loop_blocked["value"] = True
        await asyncio.sleep(0.05)
        loop_blocked["value"] = False

    blocker = asyncio.create_task(block_loop())
    await asyncio.sleep(0)

    task = {
        "id": "001",
        "phase": "01-foundation",
        "title": "T",
        "slug": "t",
        "goal": "g",
        "context": "c",
        "steps": [],
        "acceptance_criteria": [],
        "notes": [],
        "verification": "manual",
        "depends_on": [],
        "spec_refs": [],
        "priority": "high",
        "estimated_minutes": 30,
    }
    save_task = asyncio.create_task(save_tasks("sess-1", [task]))
    await asyncio.sleep(0.01)
    assert loop_blocked["value"] is True
    await save_task
    await blocker
    assert (tmp_path / "sess-1" / "tasks" / "_tasks.json").is_file()
