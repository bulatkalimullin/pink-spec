"""Tests for L4 dynamic pipeline, task merging, and completion criteria."""

from __future__ import annotations

from app.agent.pipeline_utils import (
    ensure_l4_deliverables,
    ensure_l4_task_batches,
    merge_tasks,
    normalize_pipeline_steps,
)
from app.agent.supervisor import apply_refinement, check_l4_criteria, ensure_task_coverage


def test_normalize_pipeline_steps_preserves_unique_ids():
    raw = [
        {
            "id": "tasks_backend",
            "name": "Backend Tasks",
            "executor": "builtin:task_decomposer",
            "target_count": 25,
            "prompt_focus": "02-backend only",
        },
        {
            "id": "tasks_frontend",
            "name": "Frontend Tasks",
            "executor": "builtin:task_decomposer",
            "target_count": 25,
        },
        {
            "id": "security_spec",
            "name": "Security",
            "executor": "generic",
            "artifact_key": "security_spec",
            "prompt_focus": "Threat model",
        },
    ]
    steps = normalize_pipeline_steps(raw, "L4")
    ids = [s["id"] for s in steps]
    assert ids == ["tasks_backend", "tasks_frontend", "security_spec"]
    assert steps[0]["executor_agent"] == "task_decomposer"
    assert steps[0]["target_count"] == 25


def test_merge_tasks_renumbers_globally():
    existing = [{"id": "001", "title": "First", "phase": "01-foundation"}]
    new_batch = [{"id": "001", "title": "Second", "phase": "02-backend"}]
    merged = merge_tasks(existing, new_batch)
    assert len(merged) == 2
    assert merged[0]["id"] == "001"
    assert merged[1]["id"] == "002"
    assert merged[0]["title"] == "First"
    assert merged[1]["title"] == "Second"


def test_ensure_l4_deliverables_adds_generics():
    steps = [
        {
            "id": "product_analyst",
            "name": "Product",
            "executor": "builtin:product_analyst",
            "executor_agent": "product_analyst",
            "artifact_key": "product_spec",
            "required": True,
        }
    ]
    result = ensure_l4_deliverables(steps, min_deliverables=3)
    generic = [s for s in result if s.get("executor") == "generic"]
    assert len(generic) >= 3


def test_ensure_l4_task_batches_splits_single_decomposer():
    steps = [
        {
            "id": "task_decomposer",
            "name": "Tasks",
            "executor": "builtin:task_decomposer",
            "executor_agent": "task_decomposer",
            "required": True,
        },
        {
            "id": "reviewer",
            "name": "Reviewer",
            "executor": "builtin:reviewer",
            "executor_agent": "reviewer",
            "required": True,
        },
    ]
    result = ensure_l4_task_batches(steps, tasks_per_batch=25)
    task_steps = [s for s in result if s.get("executor_agent") == "task_decomposer"]
    assert len(task_steps) >= 4
    assert task_steps[0]["id"] == "tasks_foundation"


def test_check_l4_criteria_tasks_coverage():
    state = {
        "artifacts": {"product_spec": "x", "architecture_spec": "y"},
        "review_reports": [{"passed": True, "rules_compliant": True, "confidence": 0.9}],
        "tasks": [{"id": "001"}] * 50,
        "pipeline": [
            {
                "id": "product_analyst",
                "artifact_key": "product_spec",
                "required": True,
                "executor": "builtin:product_analyst",
            },
            {
                "id": "architect",
                "artifact_key": "architecture_spec",
                "required": True,
                "executor": "builtin:architect",
            },
        ],
        "open_questions": [],
        "saturation_report": {},
        "rules": {
            "l4": {"min_tasks": 100, "tasks_coverage_pct": 95.0},
            "rag": {"enabled": False},
        },
    }
    criteria = check_l4_criteria(state)
    assert criteria["tasks_coverage"] is False
    assert criteria["artifacts_complete"] is True

    state["tasks"] = [{"id": f"{i:03d}"} for i in range(95)]
    criteria = check_l4_criteria(state)
    assert criteria["tasks_coverage"] is True


def test_apply_refinement_clears_failed_artifacts(tmp_path, monkeypatch):
    from app.services import export as export_mod

    monkeypatch.setattr(export_mod, "OUTPUT_ROOT", tmp_path)

    session_id = "refine-session"
    state = {
        "session_id": session_id,
        "pipeline": [
            {
                "id": "product_analyst",
                "artifact_key": "product_spec",
                "executor": "builtin:product_analyst",
            },
            {
                "id": "architect",
                "artifact_key": "architecture_spec",
                "executor": "builtin:architect",
            },
            {"id": "reviewer", "executor": "builtin:reviewer"},
        ],
        "agent_outputs": {
            "product_analyst": "bad",
            "architect": "good",
            "reviewer": "{}",
        },
        "artifacts": {
            "product_spec": "<3 chars>",
            "architecture_spec": "<4 chars>",
        },
    }
    from app.services.export import write_artifact

    write_artifact(session_id, "product_spec", "bad")
    write_artifact(session_id, "architecture_spec", "good")

    report = {
        "passed": False,
        "issues": [{"location": "product_spec#scope", "severity": "critical"}],
    }
    updated = apply_refinement(state, report, {"tasks_coverage": True})
    assert "product_analyst" not in updated["agent_outputs"]
    assert "architect" in updated["agent_outputs"]
    assert "product_spec" not in updated["artifacts"]
    assert "reviewer" not in updated["agent_outputs"]
    assert not (tmp_path / session_id / "docs" / "product_spec.md").is_file()
    assert (tmp_path / session_id / "docs" / "architecture_spec.md").is_file()


def test_ensure_task_coverage_appends_batch():
    state = {
        "session_id": "coverage-session",
        "spec_level": "L4",
        "tasks": [{"id": "001"}] * 10,
        "pipeline": [
            {
                "id": "tasks_foundation",
                "executor": "builtin:task_decomposer",
                "executor_agent": "task_decomposer",
            },
            {"id": "reviewer", "executor": "builtin:reviewer", "executor_agent": "reviewer"},
        ],
        "agent_outputs": {"tasks_foundation": "done"},
        "rules": {
            "l4": {
                "min_tasks": 100,
                "tasks_coverage_pct": 95,
                "tasks_per_batch": 25,
                "max_task_batches": 8,
            }
        },
    }
    updated = ensure_task_coverage(state)
    task_steps = [
        s for s in updated["pipeline"] if s.get("executor_agent") == "task_decomposer"
    ]
    assert len(task_steps) >= 2
    assert any(s["id"].startswith("tasks_extra_") for s in task_steps)


def test_ensure_task_coverage_no_reset_mid_cycle():
    """After one batch completes, must not reset and re-run foundation."""
    state = {
        "session_id": "coverage-session",
        "spec_level": "L4",
        "tasks": [{"id": f"{i:03d}"} for i in range(1, 7)],
        "pipeline": [
            {"id": "tasks_foundation", "executor": "builtin:task_decomposer", "executor_agent": "task_decomposer"},
            {"id": "tasks_backend", "executor": "builtin:task_decomposer", "executor_agent": "task_decomposer"},
            {"id": "reviewer", "executor": "builtin:reviewer", "executor_agent": "reviewer"},
        ],
        "agent_outputs": {"tasks_foundation": "6 new, 6 total"},
        "rules": {"l4": {"min_tasks": 100, "tasks_coverage_pct": 95, "max_task_batches": 2}},
    }
    updated = ensure_task_coverage(state)
    assert updated["agent_outputs"]["tasks_foundation"] == "6 new, 6 total"
    assert len(updated["tasks"]) == 6


def test_ensure_task_coverage_resets_once_when_max_batches_exhausted():
    state = {
        "session_id": "coverage-session",
        "spec_level": "L4",
        "tasks": [{"id": f"{i:03d}"} for i in range(1, 45)],
        "pipeline": [
            {"id": "tasks_foundation", "executor": "builtin:task_decomposer", "executor_agent": "task_decomposer"},
            {"id": "tasks_backend", "executor": "builtin:task_decomposer", "executor_agent": "task_decomposer"},
            {"id": "reviewer", "executor": "builtin:reviewer", "executor_agent": "reviewer"},
        ],
        "agent_outputs": {
            "tasks_foundation": "done",
            "tasks_backend": "done",
        },
        "rules": {"l4": {"min_tasks": 100, "tasks_coverage_pct": 95, "max_task_batches": 2}},
    }
    updated = ensure_task_coverage(state)
    assert "tasks_foundation" not in updated["agent_outputs"]
    assert updated["tasks"] == []
    assert updated["_task_coverage_retries"] == 1


def test_ensure_task_coverage_no_second_reset():
    state = {
        "session_id": "coverage-session",
        "spec_level": "L4",
        "tasks": [{"id": f"{i:03d}"} for i in range(1, 30)],
        "pipeline": [
            {"id": "tasks_foundation", "executor": "builtin:task_decomposer", "executor_agent": "task_decomposer"},
            {"id": "tasks_backend", "executor": "builtin:task_decomposer", "executor_agent": "task_decomposer"},
            {"id": "reviewer", "executor": "builtin:reviewer", "executor_agent": "reviewer"},
        ],
        "agent_outputs": {"tasks_foundation": "done", "tasks_backend": "done"},
        "_task_coverage_retries": 1,
        "rules": {"l4": {"min_tasks": 100, "tasks_coverage_pct": 95, "max_task_batches": 2}},
    }
    updated = ensure_task_coverage(state)
    assert updated["agent_outputs"]["tasks_foundation"] == "done"
    assert len(updated["tasks"]) == 29
    assert updated["_task_coverage_retries"] == 1
