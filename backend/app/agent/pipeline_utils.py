"""Pipeline planning helpers and legacy sequence conversion."""

from __future__ import annotations

from typing import Any

AGENT_SEQUENCE = {
    "L1": ["researcher", "product_analyst", "architect", "export"],
    "L2": ["researcher", "product_analyst", "architect", "task_decomposer", "reviewer", "export"],
    "L3": [
        "researcher",
        "product_analyst",
        "architect",
        "api_designer",
        "ui_designer",
        "context_manager",
        "task_decomposer",
        "reviewer",
        "export",
    ],
    "L4": [
        "researcher",
        "product_analyst",
        "architect",
        "api_designer",
        "ui_designer",
        "context_manager",
        "task_decomposer",
        "reviewer",
        "export",
    ],
}

BUILTIN_STEP_META: dict[str, dict[str, Any]] = {
    "researcher": {"name": "Researcher", "executor": "builtin:researcher", "artifact_key": None},
    "pipeline_planner": {
        "name": "Pipeline Planner",
        "executor": "builtin:pipeline_planner",
        "artifact_key": None,
    },
    "product_analyst": {
        "name": "Product Specification",
        "executor": "builtin:product_analyst",
        "artifact_key": "product_spec",
    },
    "architect": {
        "name": "Architecture",
        "executor": "builtin:architect",
        "artifact_key": "architecture_spec",
    },
    "api_designer": {
        "name": "API Design",
        "executor": "builtin:api_designer",
        "artifact_key": "api_spec",
    },
    "ui_designer": {
        "name": "UI Design",
        "executor": "builtin:ui_designer",
        "artifact_key": "ui_spec",
    },
    "context_manager": {
        "name": "Context Manager",
        "executor": "builtin:context_manager",
        "artifact_key": None,
    },
    "task_decomposer": {
        "name": "Task Decomposition",
        "executor": "builtin:task_decomposer",
        "artifact_key": None,
    },
    "reviewer": {"name": "Reviewer", "executor": "builtin:reviewer", "artifact_key": None},
    "export": {"name": "Export", "executor": "builtin:export", "artifact_key": None},
}

TASK_COUNT_BY_LEVEL = {"L1": 0, "L2": 20, "L3": 60, "L4": 100}

L4_DEFAULT_DELIVERABLES: list[dict[str, Any]] = [
    {
        "id": "security_spec",
        "name": "Security Specification",
        "artifact_key": "security_spec",
        "prompt_focus": "Threat model, authn/authz, data protection, compliance, security controls",
    },
    {
        "id": "data_model",
        "name": "Data Model",
        "artifact_key": "data_model",
        "prompt_focus": "Entities, relationships, indexes, migrations, data lifecycle",
    },
    {
        "id": "test_strategy",
        "name": "Test Strategy",
        "artifact_key": "test_strategy",
        "prompt_focus": "Unit, integration, e2e, performance, test data, CI gates",
    },
    {
        "id": "deployment_spec",
        "name": "Deployment Specification",
        "artifact_key": "deployment_spec",
        "prompt_focus": "Infrastructure, CI/CD, environments, rollout, rollback",
    },
    {
        "id": "observability_spec",
        "name": "Observability Specification",
        "artifact_key": "observability_spec",
        "prompt_focus": "Logging, metrics, tracing, alerting, SLOs, dashboards",
    },
    {
        "id": "risk_register",
        "name": "Risk Register",
        "artifact_key": "risk_register",
        "prompt_focus": "Technical and product risks, mitigations, owners, severity",
    },
    {
        "id": "migration_plan",
        "name": "Migration Plan",
        "artifact_key": "migration_plan",
        "prompt_focus": "Data migration, phased rollout, backward compatibility",
    },
    {
        "id": "runbook",
        "name": "Operations Runbook",
        "artifact_key": "runbook",
        "prompt_focus": "Incident response, on-call procedures, common operations",
    },
]

L4_TASK_PHASES: list[dict[str, Any]] = [
    {
        "id": "tasks_foundation",
        "name": "Tasks: Foundation",
        "prompt_focus": "01-foundation phase only: repo setup, tooling, CI, env config",
        "target_count": 25,
    },
    {
        "id": "tasks_backend",
        "name": "Tasks: Backend",
        "prompt_focus": "02-backend phase only: API, services, database, business logic",
        "target_count": 25,
    },
    {
        "id": "tasks_frontend",
        "name": "Tasks: Frontend",
        "prompt_focus": "03-frontend phase only: UI components, pages, state, routing",
        "target_count": 25,
    },
    {
        "id": "tasks_integration",
        "name": "Tasks: Integration",
        "prompt_focus": "04-integration phase: E2E wiring, third-party integrations, deployment",
        "target_count": 25,
    },
]


def step_builtin_agent_id(step: dict[str, Any]) -> str | None:
    if step.get("executor_agent"):
        return step["executor_agent"]
    executor = step.get("executor", "")
    if executor.startswith("builtin:"):
        return executor.split(":", 1)[1]
    return None


def normalize_pipeline_steps(steps: list[dict], spec_level: str) -> list[dict[str, Any]]:
    """Normalize LLM-planned steps, preserving unique step ids."""
    out: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for s in steps:
        if not isinstance(s, dict) or not s.get("id"):
            continue
        step_id = s["id"]
        if step_id in ("researcher", "pipeline_planner", "export"):
            continue
        if step_id in seen_ids:
            step_id = f"{step_id}_{len(seen_ids)}"
        seen_ids.add(step_id)

        executor = s.get("executor", "generic")
        if executor.startswith("builtin:"):
            builtin_id = executor.split(":", 1)[1]
            if builtin_id in BUILTIN_STEP_META:
                meta = BUILTIN_STEP_META[builtin_id]
                out.append(
                    {
                        "id": step_id,
                        "name": s.get("name") or meta["name"],
                        "executor": meta["executor"],
                        "executor_agent": builtin_id,
                        "artifact_key": s.get("artifact_key", meta.get("artifact_key")),
                        "required": s.get("required", True),
                        "target_count": s.get("target_count")
                        if builtin_id == "task_decomposer"
                        else None,
                        "prompt_focus": s.get("prompt_focus"),
                    }
                )
                continue
        out.append(
            {
                "id": step_id,
                "name": s.get("name", step_id.replace("_", " ").title()),
                "executor": executor if executor == "generic" else "generic",
                "executor_agent": None,
                "artifact_key": s.get("artifact_key", step_id),
                "required": s.get("required", True),
                "prompt_focus": s.get("prompt_focus", s.get("description", "")),
                "target_count": s.get("target_count"),
            }
        )
    return out


def merge_tasks(existing: list[dict[str, Any]], new_tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge task batches and renumber IDs globally."""
    merged = list(existing)
    for task in new_tasks:
        merged.append(dict(task))
    for i, task in enumerate(merged, start=1):
        task["id"] = f"{i:03d}"
    return merged


def count_task_decomposer_steps(pipeline: list[dict[str, Any]]) -> int:
    return sum(
        1
        for s in pipeline
        if step_builtin_agent_id(s) == "task_decomposer" or s.get("id") == "task_decomposer"
    )


def append_extra_task_batch(
    pipeline: list[dict[str, Any]], batch_num: int, target_count: int, focus: str
) -> list[dict[str, Any]]:
    step_id = f"tasks_extra_{batch_num}"
    if any(s.get("id") == step_id for s in pipeline):
        return pipeline
    reviewer_idx = next(
        (i for i, s in enumerate(pipeline) if step_builtin_agent_id(s) == "reviewer"),
        len(pipeline),
    )
    new_step = {
        "id": step_id,
        "name": f"Tasks: Extra Batch {batch_num}",
        "executor": "builtin:task_decomposer",
        "executor_agent": "task_decomposer",
        "artifact_key": None,
        "required": True,
        "target_count": target_count,
        "prompt_focus": focus,
    }
    updated = list(pipeline)
    updated.insert(reviewer_idx, new_step)
    return updated


def ensure_l4_deliverables(
    steps: list[dict[str, Any]], min_deliverables: int
) -> list[dict[str, Any]]:
    """Add default generic deliverables until min_deliverables is reached."""
    generic_count = sum(1 for s in steps if s.get("executor") == "generic")
    if generic_count >= min_deliverables:
        return steps
    existing_keys = {s.get("artifact_key") for s in steps if s.get("artifact_key")}
    insert_at = next(
        (
            i
            for i, s in enumerate(steps)
            if step_builtin_agent_id(s) in ("context_manager", "task_decomposer")
        ),
        len(steps),
    )
    updated = list(steps)
    for d in L4_DEFAULT_DELIVERABLES:
        if generic_count >= min_deliverables:
            break
        if d["artifact_key"] in existing_keys:
            continue
        updated.insert(
            insert_at,
            {
                "id": d["id"],
                "name": d["name"],
                "executor": "generic",
                "artifact_key": d["artifact_key"],
                "required": False,
                "prompt_focus": d["prompt_focus"],
            },
        )
        insert_at += 1
        existing_keys.add(d["artifact_key"])
        generic_count += 1
    return updated


def ensure_l4_task_batches(steps: list[dict[str, Any]], tasks_per_batch: int) -> list[dict[str, Any]]:
    """Ensure L4 has multiple task decomposer steps if only one exists."""
    task_steps = [
        s for s in steps if step_builtin_agent_id(s) == "task_decomposer"
    ]
    if len(task_steps) >= 2:
        return steps
    reviewer_idx = next(
        (i for i, s in enumerate(steps) if step_builtin_agent_id(s) == "reviewer"),
        len(steps),
    )
    updated = [s for s in steps if step_builtin_agent_id(s) != "task_decomposer"]
    insert_at = next(
        (
            i
            for i, s in enumerate(updated)
            if step_builtin_agent_id(s) == "reviewer"
        ),
        len(updated),
    )
    if insert_at == len(updated) and reviewer_idx < len(steps):
        insert_at = reviewer_idx
    for phase in L4_TASK_PHASES:
        updated.insert(
            insert_at,
            {
                "id": phase["id"],
                "name": phase["name"],
                "executor": "builtin:task_decomposer",
                "executor_agent": "task_decomposer",
                "artifact_key": None,
                "required": True,
                "target_count": phase.get("target_count", tasks_per_batch),
                "prompt_focus": phase["prompt_focus"],
            },
        )
        insert_at += 1
    return updated


def legacy_sequence_to_steps(spec_level: str) -> list[dict[str, Any]]:
    """Convert fixed AGENT_SEQUENCE to pipeline step dicts."""
    sequence = AGENT_SEQUENCE.get(spec_level, AGENT_SEQUENCE["L2"])
    steps: list[dict[str, Any]] = []
    for agent_id in sequence:
        if agent_id == "export":
            continue
        meta = BUILTIN_STEP_META.get(agent_id, {})
        step: dict[str, Any] = {
            "id": agent_id,
            "name": meta.get("name", agent_id.replace("_", " ").title()),
            "executor": meta.get("executor", f"builtin:{agent_id}"),
            "executor_agent": agent_id,
            "artifact_key": meta.get("artifact_key"),
            "required": True,
        }
        if agent_id == "task_decomposer":
            step["target_count"] = TASK_COUNT_BY_LEVEL.get(spec_level, 20)
        steps.append(step)
    return steps


def initial_auto_pipeline(spec_level: str) -> list[dict[str, Any]]:
    """Pipeline before planner runs: researcher then planner."""
    steps = [
        {
            "id": "researcher",
            "name": "Researcher",
            "executor": "builtin:researcher",
            "artifact_key": None,
            "required": False,
        },
        {
            "id": "pipeline_planner",
            "name": "Pipeline Planner",
            "executor": "builtin:pipeline_planner",
            "artifact_key": None,
            "required": True,
        },
    ]
    return steps


def get_routing_sequence(state: dict[str, Any]) -> list[str]:
    """Step ids for supervisor routing (includes export sentinel)."""
    pipeline = state.get("pipeline") or []
    ids = [s["id"] for s in pipeline if s.get("id") != "export"]
    ids.append("export")
    return ids


def required_artifact_keys(pipeline: list[dict[str, Any]]) -> set[str]:
    keys: set[str] = set()
    for step in pipeline:
        key = step.get("artifact_key")
        if key and step.get("required", True) and step.get("executor") != "builtin:task_decomposer":
            keys.add(key)
    return keys


def merge_deliverables_into_steps(
    steps: list[dict[str, Any]],
    deliverables: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Ensure user deliverables are present; honor skip flags."""
    skip_keys = {d["artifact_key"] for d in deliverables if d.get("skip")}
    skip_builtin = set()
    for key in skip_keys:
        for bid, meta in BUILTIN_STEP_META.items():
            if meta.get("artifact_key") == key:
                skip_builtin.add(bid)

    filtered = [
        s for s in steps if s["id"] not in skip_builtin and s.get("artifact_key") not in skip_keys
    ]

    existing_keys = {s.get("artifact_key") for s in filtered if s.get("artifact_key")}
    for d in deliverables:
        if d.get("skip"):
            continue
        if d["artifact_key"] in existing_keys:
            continue
        filtered.insert(
            max(len(filtered) - 2, 0),
            {
                "id": d.get("id", d["artifact_key"]),
                "name": d["name"],
                "executor": "generic",
                "artifact_key": d["artifact_key"],
                "required": d.get("required", True),
                "prompt_focus": d.get("prompt_hint") or d.get("description", ""),
            },
        )
        existing_keys.add(d["artifact_key"])
    return filtered
