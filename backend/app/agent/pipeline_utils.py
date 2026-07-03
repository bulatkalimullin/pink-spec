"""Pipeline planning helpers and legacy sequence conversion."""

from __future__ import annotations

from typing import Any

from app.agent.domain_profiles import (
    get_domain_deliverables,
    get_domain_work_packages,
    work_packages_to_pipeline_steps,
)

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
    pipeline: list[dict[str, Any]],
    batch_num: int,
    target_count: int,
    focus: str,
    *,
    domain: str = "general",
) -> list[dict[str, Any]]:
    step_id = f"wp_extra_{batch_num}"
    if any(s.get("id") == step_id for s in pipeline):
        return pipeline
    reviewer_idx = next(
        (i for i, s in enumerate(pipeline) if step_builtin_agent_id(s) == "reviewer"),
        len(pipeline),
    )
    phase_slug = f"99-extra-{batch_num}"
    new_step = {
        "id": step_id,
        "name": f"Work Package: Extra Batch {batch_num}",
        "executor": "builtin:task_decomposer",
        "executor_agent": "task_decomposer",
        "artifact_key": None,
        "required": True,
        "target_count": target_count,
        "prompt_focus": (
            f"Work package phase '{phase_slug}': {focus}. "
            f"Use phase slug '{phase_slug}' for all tasks in this batch."
        ),
        "work_package_phase": phase_slug,
    }
    updated = list(pipeline)
    updated.insert(reviewer_idx, new_step)
    return updated


def ensure_domain_deliverables(
    steps: list[dict[str, Any]],
    domain: str,
    min_deliverables: int,
    maturity: str | None = None,
) -> list[dict[str, Any]]:
    """Add domain-profile generic deliverables until min_deliverables is reached."""
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
    for d in get_domain_deliverables(domain, maturity):
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
                "required": d.get("required", False),
                "prompt_focus": d["prompt_focus"],
            },
        )
        insert_at += 1
        existing_keys.add(d["artifact_key"])
        generic_count += 1
    return updated


def ensure_domain_work_packages(
    steps: list[dict[str, Any]],
    domain: str,
    tasks_per_batch: int | None = None,
    maturity: str | None = None,
) -> list[dict[str, Any]]:
    """Ensure domain work packages exist when task decomposer has fewer than 2 steps."""
    task_steps = [s for s in steps if step_builtin_agent_id(s) == "task_decomposer"]
    expected_wp = get_domain_work_packages(domain, maturity)
    existing_wp_ids = {s.get("id") for s in task_steps}
    missing_wp = [wp for wp in expected_wp if wp["id"] not in existing_wp_ids]

    if len(task_steps) >= 2 and not missing_wp:
        return steps

    reviewer_idx = next(
        (i for i, s in enumerate(steps) if step_builtin_agent_id(s) == "reviewer"),
        len(steps),
    )
    updated = [s for s in steps if step_builtin_agent_id(s) != "task_decomposer"]
    insert_at = next(
        (i for i, s in enumerate(updated) if step_builtin_agent_id(s) == "reviewer"),
        len(updated),
    )
    if insert_at == len(updated) and reviewer_idx < len(steps):
        insert_at = reviewer_idx

    wp_steps = work_packages_to_pipeline_steps(
        expected_wp if not task_steps else missing_wp,
        tasks_per_batch_override=tasks_per_batch,
    )
    for wp_step in wp_steps:
        if wp_step.get("id") in existing_wp_ids:
            continue
        updated.insert(insert_at, wp_step)
        insert_at += 1
        existing_wp_ids.add(wp_step.get("id"))
    return updated


PROD_SPLIT_DELIVERABLES: dict[str, list[dict[str, str]]] = {
    "security_spec": [
        {"id": "threat_model", "name": "Threat Model", "artifact_key": "threat_model"},
        {"id": "security_controls", "name": "Security Controls", "artifact_key": "security_controls"},
    ],
    "deployment_spec": [
        {"id": "cicd_spec", "name": "CI/CD Specification", "artifact_key": "cicd_spec"},
        {"id": "environment_spec", "name": "Environment Specification", "artifact_key": "environment_spec"},
    ],
}


def expand_prod_deliverables(
    steps: list[dict[str, Any]],
    domain: str,
    maturity: str | None,
) -> list[dict[str, Any]]:
    """Split combined deliverables into finer production steps when maturity is production+."""
    from app.agent.spec_maturity import is_production_maturity

    if not maturity or not is_production_maturity(maturity) or domain != "software":
        return steps

    existing_keys = {s.get("artifact_key") for s in steps if s.get("artifact_key")}
    updated: list[dict[str, Any]] = []

    for step in steps:
        key = step.get("artifact_key")
        if key in PROD_SPLIT_DELIVERABLES:
            parts = PROD_SPLIT_DELIVERABLES[key]
            if all(p["artifact_key"] not in existing_keys for p in parts):
                for part in parts:
                    updated.append(
                        {
                            "id": part["id"],
                            "name": part["name"],
                            "executor": "generic",
                            "artifact_key": part["artifact_key"],
                            "required": step.get("required", True),
                            "prompt_focus": step.get("prompt_focus", part["name"]),
                        }
                    )
                    existing_keys.add(part["artifact_key"])
                continue
        updated.append(step)

    return updated


def named_prod_fillers(
    domain: str,
    maturity: str | None,
    existing_keys: set[str],
    count: int,
) -> list[dict[str, Any]]:
    """Named prod deliverables instead of generic_extra_N."""
    from app.agent.spec_maturity import is_production_maturity

    fillers: list[dict[str, Any]] = []
    if not is_production_maturity(maturity or "mvp"):
        return fillers
    for d in get_domain_deliverables(domain, maturity):
        if len(fillers) >= count:
            break
        if d["artifact_key"] in existing_keys:
            continue
        fillers.append(
            {
                "id": d["id"],
                "name": d["name"],
                "executor": "generic",
                "artifact_key": d["artifact_key"],
                "required": False,
                "prompt_focus": d["prompt_focus"],
            }
        )
        existing_keys.add(d["artifact_key"])
    return fillers


def insert_pipeline_steps_before_reviewer(
    pipeline: list[dict[str, Any]],
    new_steps: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Insert new steps immediately before the reviewer step."""
    if not new_steps:
        return pipeline
    existing_ids = {s.get("id") for s in pipeline}
    reviewer_idx = next(
        (i for i, s in enumerate(pipeline) if step_builtin_agent_id(s) == "reviewer"),
        len(pipeline),
    )
    updated = list(pipeline)
    offset = 0
    for step in new_steps:
        if step.get("id") in existing_ids:
            continue
        updated.insert(reviewer_idx + offset, step)
        existing_ids.add(step.get("id"))
        offset += 1
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
