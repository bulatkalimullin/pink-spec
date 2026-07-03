"""Tests for L4 dynamic pipeline, domain profiles, and completion criteria."""

from __future__ import annotations

import pytest

from app.agent.domain_profiles import detect_domain, get_domain_deliverables, get_domain_work_packages
from app.agent.pipeline_utils import (
    ensure_domain_deliverables,
    ensure_domain_work_packages,
    insert_pipeline_steps_before_reviewer,
    merge_tasks,
    normalize_pipeline_steps,
)
from app.agent.agents.pipeline_planner import (
    PipelinePlannerAgent,
    _fallback_domain_steps,
    apply_domain_l4_rules,
)
from app.agent.supervisor import (
    _route_next,
    check_l4_criteria,
    ensure_task_coverage,
)


def test_detect_domain_education():
    idea = "Учебно-методический материал по продвинутому Python для начинающих"
    assert detect_domain(idea, "general") == "education"


def test_detect_domain_embedded():
    idea = "Автопилот для FPV дрона на Raspberry Pi 5"
    assert detect_domain(idea, "general") == "embedded"


def test_education_deliverables_no_api_spec():
    keys = {d["artifact_key"] for d in get_domain_deliverables("education")}
    assert "lesson_plan" in keys
    assert "api_spec" not in keys
    assert "ui_spec" not in keys


def test_software_production_merge_adds_observability():
    mvp_keys = {d["artifact_key"] for d in get_domain_deliverables("software", "mvp")}
    prod_keys = {d["artifact_key"] for d in get_domain_deliverables("software", "production")}
    assert "observability_spec" not in mvp_keys
    assert "observability_spec" in prod_keys
    assert "operational_spec" in prod_keys


def test_embedded_production_snapshot_deliverables():
    keys = {d["artifact_key"] for d in get_domain_deliverables("embedded", "production")}
    assert len(keys) >= 10
    assert "ota_update_spec" in keys
    assert "manufacturing_spec" in keys


def test_education_work_packages_not_web_phases():
    phases = [wp["phase"] for wp in get_domain_work_packages("education")]
    assert "01-design" in phases
    assert "02-content" in phases
    assert not any("foundation" in p or "backend" in p for p in phases)


def test_normalize_pipeline_steps_preserves_unique_ids():
    raw = [
        {
            "id": "wp_content",
            "name": "Content Work Package",
            "executor": "builtin:task_decomposer",
            "target_count": 8,
            "prompt_focus": "02-content phase only",
        },
        {
            "id": "lesson_plan",
            "name": "Lesson Plan",
            "executor": "generic",
            "artifact_key": "lesson_plan",
            "prompt_focus": "Calendar plan",
        },
    ]
    steps = normalize_pipeline_steps(raw, "L4")
    ids = [s["id"] for s in steps]
    assert ids == ["wp_content", "lesson_plan"]
    assert steps[0]["executor_agent"] == "task_decomposer"


def test_merge_tasks_renumbers_globally():
    existing = [{"id": "001", "title": "First", "phase": "01-design"}]
    new_batch = [{"id": "001", "title": "Second", "phase": "02-content"}]
    merged = merge_tasks(existing, new_batch)
    assert len(merged) == 2
    assert merged[1]["id"] == "002"
    assert merged[1]["phase"] == "02-content"


def test_ensure_domain_deliverables_education():
    steps = [
        {
            "id": "product_spec",
            "name": "TZ",
            "executor": "generic",
            "artifact_key": "product_spec",
            "required": True,
        }
    ]
    result = ensure_domain_deliverables(steps, "education", min_deliverables=4)
    generic = [s for s in result if s.get("executor") == "generic"]
    keys = {s.get("artifact_key") for s in generic}
    assert len(generic) >= 4
    assert "lesson_plan" in keys


def test_ensure_domain_work_packages_education():
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
    result = ensure_domain_work_packages(steps, "education", tasks_per_batch=8)
    task_steps = [s for s in result if s.get("executor_agent") == "task_decomposer"]
    assert len(task_steps) >= 3
    assert task_steps[0]["id"] == "wp_design"
    assert "01-design" in task_steps[0].get("prompt_focus", "")


def test_fallback_domain_steps_education_no_web():
    steps = _fallback_domain_steps("L4", "education")
    artifact_keys = {s.get("artifact_key") for s in steps if s.get("artifact_key")}
    ids = {s.get("id") for s in steps}
    assert "api_spec" not in artifact_keys
    assert "wp_design" in ids or any(s.get("executor_agent") == "task_decomposer" for s in steps)


def test_apply_domain_l4_rules_education_lowers_min_tasks():
    rules = {
        "spec_level": "L4",
        "project": {"domain": "education"},
        "l4": {"min_tasks": 100, "tasks_per_batch": 25},
    }
    updated = apply_domain_l4_rules(rules)
    assert updated["l4"]["min_tasks"] == 20
    assert updated["l4"]["tasks_per_batch"] == 8


def test_insert_pipeline_steps_before_reviewer():
    pipeline = [
        {"id": "lesson_plan", "executor": "generic", "artifact_key": "lesson_plan"},
        {"id": "reviewer", "executor": "builtin:reviewer", "executor_agent": "reviewer"},
    ]
    new_steps = [
        {"id": "delta_assessment", "executor": "generic", "artifact_key": "assessment_system"},
    ]
    result = insert_pipeline_steps_before_reviewer(pipeline, new_steps)
    assert [s["id"] for s in result] == ["lesson_plan", "delta_assessment", "reviewer"]


def test_check_l4_criteria_tasks_coverage_education():
    state = {
        "session_id": "s1",
        "artifacts": {"product_spec": "x", "lesson_plan": "y"},
        "review_reports": [{"passed": True, "rules_compliant": True, "confidence": 0.9}],
        "tasks": [{"id": "001"}] * 18,
        "pipeline": [
            {
                "id": "product_spec",
                "artifact_key": "product_spec",
                "required": True,
                "executor": "generic",
            },
            {
                "id": "lesson_plan",
                "artifact_key": "lesson_plan",
                "required": True,
                "executor": "generic",
            },
        ],
        "open_questions": [],
        "saturation_report": {},
        "rules": {
            "l4": {"min_tasks": 20, "tasks_coverage_pct": 95.0},
            "rag": {"enabled": False},
        },
    }
    criteria = check_l4_criteria(state)
    assert criteria["artifacts_complete"] is True
    assert criteria["tasks_coverage"] is False

    state["tasks"] = [{"id": f"{i:03d}"} for i in range(19)]
    criteria = check_l4_criteria(state)
    assert criteria["tasks_coverage"] is True


def test_pipeline_planner_strips_web_for_education():
    agent = PipelinePlannerAgent(llm=None)
    steps = [
        {"id": "api_spec", "executor": "generic", "artifact_key": "api_spec"},
        {"id": "lesson_plan", "executor": "generic", "artifact_key": "lesson_plan"},
        {"id": "ui_designer", "executor": "builtin:ui_designer", "executor_agent": "ui_designer"},
    ]
    result = agent._apply_idea_heuristics(steps, "УМК Python", "education")
    keys = {s.get("artifact_key") for s in result}
    ids = {s.get("id") for s in result}
    assert "api_spec" not in keys
    assert "ui_designer" not in ids
    assert "lesson_plan" in keys


def test_ensure_task_coverage_appends_wp_extra_batch():
    state = {
        "session_id": "coverage-session",
        "spec_level": "L4",
        "idea": "УМК Python",
        "tasks": [{"id": "001"}] * 5,
        "pipeline": [
            {
                "id": "wp_design",
                "executor": "builtin:task_decomposer",
                "executor_agent": "task_decomposer",
            },
            {"id": "reviewer", "executor": "builtin:reviewer", "executor_agent": "reviewer"},
        ],
        "agent_outputs": {"wp_design": "done"},
        "rules": {
            "project": {"domain": "education"},
            "l4": {
                "min_tasks": 20,
                "tasks_coverage_pct": 95,
                "tasks_per_batch": 8,
                "max_task_batches": 8,
            },
        },
    }
    updated = ensure_task_coverage(state)
    task_steps = [s for s in updated["pipeline"] if s.get("executor_agent") == "task_decomposer"]
    assert len(task_steps) >= 2
    assert any(s["id"].startswith("wp_extra_") for s in task_steps)


@pytest.mark.asyncio
async def test_plan_pipeline_delta_heuristic_missing_keys():
    from app.agent.agents.pipeline_planner import plan_pipeline_delta

    state = {
        "session_id": "delta-session",
        "idea": "УМК Python",
        "spec_level": "L4",
        "artifacts": {"product_spec": "x"},
        "pipeline": [
            {"id": "product_spec", "artifact_key": "product_spec", "executor": "generic"},
            {"id": "reviewer", "executor": "builtin:reviewer", "executor_agent": "reviewer"},
        ],
        "rules": {"project": {"domain": "education"}},
    }
    report = {
        "passed": False,
        "confidence": 0.5,
        "issues": [
            {
                "severity": "critical",
                "description": "missing lesson_plan",
                "location": "lesson_plan#general",
            }
        ],
    }

    class StubLLM:
        async def generate(self, *args, **kwargs):
            return '{"steps": [], "reasoning": "none"}'

    new_steps, reasoning = await plan_pipeline_delta(state, StubLLM(), report)
    assert any(s.get("artifact_key") == "lesson_plan" for s in new_steps)
    assert reasoning


def test_route_next_prefers_refinement_fixer_when_pending():
    state = {
        "pipeline": [{"id": "reviewer", "executor": "builtin:reviewer"}],
        "agent_outputs": {"product_analyst": "done", "reviewer": "done"},
        "refinement_pending": True,
        "spec_level": "L4",
    }
    assert _route_next(state) == "refinement_fixer"
