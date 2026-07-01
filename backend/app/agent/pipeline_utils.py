"""Pipeline planning helpers and legacy sequence conversion."""
from __future__ import annotations

from typing import Any

from app.schemas.pipeline import PipelineStep

AGENT_SEQUENCE = {
    "L1": ["researcher", "product_analyst", "architect", "export"],
    "L2": ["researcher", "product_analyst", "architect", "task_decomposer", "reviewer", "export"],
    "L3": [
        "researcher", "product_analyst", "architect", "api_designer", "ui_designer",
        "context_manager", "task_decomposer", "reviewer", "export",
    ],
    "L4": [
        "researcher", "product_analyst", "architect", "api_designer", "ui_designer",
        "context_manager", "task_decomposer", "reviewer", "export",
    ],
}

BUILTIN_STEP_META: dict[str, dict[str, Any]] = {
    "researcher": {"name": "Researcher", "executor": "builtin:researcher", "artifact_key": None},
    "pipeline_planner": {"name": "Pipeline Planner", "executor": "builtin:pipeline_planner", "artifact_key": None},
    "product_analyst": {"name": "Product Specification", "executor": "builtin:product_analyst", "artifact_key": "product_spec"},
    "architect": {"name": "Architecture", "executor": "builtin:architect", "artifact_key": "architecture_spec"},
    "api_designer": {"name": "API Design", "executor": "builtin:api_designer", "artifact_key": "api_spec"},
    "ui_designer": {"name": "UI Design", "executor": "builtin:ui_designer", "artifact_key": "ui_spec"},
    "context_manager": {"name": "Context Manager", "executor": "builtin:context_manager", "artifact_key": None},
    "task_decomposer": {"name": "Task Decomposition", "executor": "builtin:task_decomposer", "artifact_key": None},
    "reviewer": {"name": "Reviewer", "executor": "builtin:reviewer", "artifact_key": None},
    "export": {"name": "Export", "executor": "builtin:export", "artifact_key": None},
}

TASK_COUNT_BY_LEVEL = {"L1": 0, "L2": 20, "L3": 60, "L4": 100}


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


def step_builtin_agent_id(step: dict[str, Any]) -> str | None:
    executor = step.get("executor", "")
    if executor.startswith("builtin:"):
        return executor.split(":", 1)[1]
    return None


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

    filtered = [s for s in steps if s["id"] not in skip_builtin and s.get("artifact_key") not in skip_keys]

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
