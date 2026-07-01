"""Tests for session control and replan."""

from __future__ import annotations

from app.services.session_control import (
    apply_control_directives,
    reset_task_decomposer_steps,
    trigger_replan,
)


def _base_state():
    return {
        "session_id": "test-session",
        "spec_level": "L4",
        "agent_outputs": {
            "researcher": "done",
            "pipeline_planner": "planned",
            "product_analyst": "spec",
            "reviewer": "{}",
        },
        "artifacts": {"product_spec": "x"},
        "tasks": [{"id": "001"}],
        "pipeline": [
            {"id": "product_analyst", "executor": "builtin:product_analyst", "executor_agent": "product_analyst"},
            {"id": "tasks_foundation", "executor": "builtin:task_decomposer", "executor_agent": "task_decomposer"},
            {"id": "reviewer", "executor": "builtin:reviewer", "executor_agent": "reviewer"},
        ],
        "pipeline_planned": True,
        "review_cycles": 3,
        "rules": {"resilience": {"max_review_cycles": 10}, "l4": {"completion_confidence": 0.85}},
    }


def test_trigger_replan_resets_pipeline(tmp_path, monkeypatch):
    from app.services import export as export_mod
    from app.services.export import write_artifact

    monkeypatch.setattr(export_mod, "OUTPUT_ROOT", tmp_path)
    state = _base_state()
    write_artifact(state["session_id"], "product_spec", "x")

    state = trigger_replan(state)
    assert state["pipeline_planned"] is False
    assert state["pipeline"][0]["id"] == "pipeline_planner"
    assert "product_analyst" not in state["agent_outputs"]
    assert state["artifacts"] == {}
    assert state["review_cycles"] == 0
    assert not (tmp_path / state["session_id"] / "docs").exists()


def test_reset_task_decomposer_clears_batches(tmp_path, monkeypatch):
    import asyncio

    from app.services import export as export_mod
    from app.services.artifact_store import save_tasks

    monkeypatch.setattr(export_mod, "OUTPUT_ROOT", tmp_path)

    async def noop_save_manifest(_sid: str, _manifest: dict) -> None:
        pass

    monkeypatch.setattr("app.services.artifact_store.save_manifest", noop_save_manifest)

    asyncio.run(
        save_tasks(
            "test-session",
            [
                {
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
            ],
        )
    )

    state = reset_task_decomposer_steps(_base_state())
    assert "tasks_foundation" not in state["agent_outputs"]
    assert "reviewer" not in state["agent_outputs"]
    assert state["tasks"] == []
    assert not (tmp_path / "test-session" / "tasks").exists()


def test_apply_control_replan_directive():
    state = apply_control_directives(_base_state(), [{"action": "replan_pipeline"}])
    assert state["pipeline_planned"] is False


def test_apply_control_settings_override():
    state = apply_control_directives(
        _base_state(),
        [{"action": "update_settings", "max_review_cycles": 20}],
    )
    assert state["rules"]["resilience"]["max_review_cycles"] == 20
