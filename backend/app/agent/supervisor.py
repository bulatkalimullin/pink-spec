"""Supervisor agent — routing, quality gates, time budget, L4 completion criteria."""

from __future__ import annotations

import re
import time
from typing import Any

import structlog

from app.agent.pipeline_utils import (
    AGENT_SEQUENCE,
    append_extra_task_batch,
    count_task_decomposer_steps,
    get_routing_sequence,
    required_artifact_keys,
    step_builtin_agent_id,
)
from app.agent.state import MultiAgentState
from app.services.log_bus import log_bus

logger = structlog.get_logger(__name__)

ANTI_LOOP_LIMIT = 5
ANTI_LOOP_LIMIT_L4 = 15
MAX_REVIEW_CYCLES_DEFAULT = 10


def anti_loop_limit(spec_level: str) -> int:
    return ANTI_LOOP_LIMIT_L4 if spec_level == "L4" else ANTI_LOOP_LIMIT


async def supervisor_node(state: MultiAgentState) -> dict[str, Any]:
    session_id = state["session_id"]
    spec_level = state["spec_level"]
    started_at = state["started_at"]
    elapsed = time.time() - started_at

    time_budget = state.get("time_budget_sec")
    safety_cap = state.get("safety_cap_sec", 7200)
    max_review = (
        state["rules"].get("resilience", {}).get("max_review_cycles", MAX_REVIEW_CYCLES_DEFAULT)
    )

    hard_limit = safety_cap if spec_level == "L4" else time_budget
    if hard_limit and elapsed >= hard_limit:
        await log_bus.emit(
            session_id,
            "log_entry",
            {
                "level": "warn",
                "agent_id": "supervisor",
                "message": f"Time limit reached ({int(elapsed)}s). Forcing export.",
            },
        )
        return {**state, "current_agent": "export", "status": "degraded"}

    if time_budget and elapsed >= time_budget * 0.85:
        remaining = int(time_budget - elapsed)
        await log_bus.emit(
            session_id, "budget_warning", {"remaining_sec": remaining, "mode": "time_budget"}
        )

    call_counts = state.get("agent_call_counts", {})
    loop_limit = anti_loop_limit(spec_level)

    if spec_level == "L4":
        state = ensure_task_coverage(state)

    next_agent = _route_next(state)
    if next_agent != "export" and call_counts.get(next_agent, 0) >= loop_limit:
        logger.warning("anti_loop_triggered", agent=next_agent, session_id=session_id)
        await log_bus.emit(
            session_id,
            "log_entry",
            {
                "level": "warn",
                "agent_id": "supervisor",
                "message": f"Anti-loop: {next_agent} called {loop_limit}+ times. Skipping.",
            },
        )
        skip_agent = _skip_to_next(state, stuck_agent=next_agent, loop_limit=loop_limit)
        return {**state, "current_agent": skip_agent}

    if state.get("review_cycles", 0) >= max_review:
        await log_bus.emit(
            session_id,
            "log_entry",
            {
                "level": "warn",
                "agent_id": "supervisor",
                "message": f"Max review cycles ({max_review}) reached. Forcing export.",
            },
        )
        return {**state, "current_agent": "export", "status": "degraded"}

    remaining_sec = int(hard_limit - elapsed) if hard_limit else None
    next_step = _find_step(state, next_agent)

    await log_bus.emit(
        session_id,
        "supervisor_routing",
        {
            "next_agent": next_agent,
            "next_step_name": next_step.get("name") if next_step else next_agent,
            "reason": _routing_reason(state, next_agent),
            "remaining_sec": remaining_sec,
        },
    )

    new_counts = {**call_counts, next_agent: call_counts.get(next_agent, 0) + 1}
    return {
        **state,
        "current_agent": next_agent,
        "current_step": next_step,
        "agent_call_counts": new_counts,
    }


async def handle_l4_post_review(state: MultiAgentState) -> dict[str, Any]:
    """Evaluate L4 completion after reviewer; trigger refinement or export."""
    session_id = state["session_id"]
    spec_level = state["spec_level"]
    if spec_level != "L4":
        return {}

    criteria = check_l4_criteria(state)
    all_met = all(criteria.values())
    await log_bus.emit(
        session_id, "completion_check", {"criteria": criteria, "all_met": all_met}
    )

    review_reports = state.get("review_reports", [])
    last_report = review_reports[-1] if review_reports else {}
    passed = last_report.get("passed", False)
    confidence = last_report.get("confidence", 0)
    min_confidence = state["rules"].get("l4", {}).get("completion_confidence", 0.85)

    if all_met and passed and confidence >= min_confidence:
        await log_bus.emit(
            session_id,
            "log_entry",
            {
                "level": "info",
                "agent_id": "supervisor",
                "message": "L4 completion criteria met. Proceeding to export.",
            },
        )
        return {"current_agent": "export"}

    max_review = state["rules"].get("resilience", {}).get("max_review_cycles", MAX_REVIEW_CYCLES_DEFAULT)
    if state.get("review_cycles", 0) >= max_review:
        await log_bus.emit(
            session_id,
            "log_entry",
            {
                "level": "warn",
                "agent_id": "supervisor",
                "message": "L4 criteria not met but max review cycles reached. Exporting partial.",
            },
        )
        return {"current_agent": "export", "status": "degraded"}

    updated = apply_refinement(state, last_report)
    updated = ensure_task_coverage(updated)

    await log_bus.emit(
        session_id,
        "log_entry",
        {
            "level": "info",
            "agent_id": "supervisor",
            "message": f"L4 refinement cycle #{updated.get('review_cycles', 0)}: re-running failed steps",
        },
    )
    return {**updated, "current_agent": "supervisor"}


def ensure_task_coverage(state: MultiAgentState) -> MultiAgentState:
    """Append extra task batch steps if L4 task count is below coverage threshold."""
    if state.get("spec_level") != "L4":
        return state

    rules = state.get("rules", {})
    l4 = rules.get("l4", {}) or {}
    min_tasks = l4.get("min_tasks", 100)
    pct = l4.get("tasks_coverage_pct", 95.0)
    required = int(min_tasks * pct / 100)
    tasks = state.get("tasks", [])

    if len(tasks) >= required:
        return state

    pipeline = list(state.get("pipeline") or [])
    batch_count = count_task_decomposer_steps(pipeline)
    max_batches = l4.get("max_task_batches", 8)
    if batch_count >= max_batches:
        return state

    # Only add batches when all existing task steps are complete
    outputs = state.get("agent_outputs", {})
    pending_task_steps = [
        s["id"]
        for s in pipeline
        if step_builtin_agent_id(s) == "task_decomposer" and s["id"] not in outputs
    ]
    if pending_task_steps:
        return state

    batch_num = batch_count + 1
    tasks_per_batch = l4.get("tasks_per_batch", 25)
    pipeline = append_extra_task_batch(
        pipeline,
        batch_num,
        tasks_per_batch,
        f"Generate additional tasks to reach at least {required} total. Avoid duplicates.",
    )
    return {**state, "pipeline": pipeline}


def apply_refinement(state: MultiAgentState, report: dict[str, Any]) -> MultiAgentState:
    """Clear outputs for artifacts that failed review so they can be regenerated."""
    issues = report.get("issues", [])
    artifact_keys: set[str] = set()

    for issue in issues:
        loc = issue.get("location", "")
        key = _parse_artifact_key(loc)
        if key:
            artifact_keys.add(key)

    if not artifact_keys and not report.get("passed", True):
        pipeline = state.get("pipeline") or []
        artifact_keys = {
            s.get("artifact_key")
            for s in pipeline
            if s.get("artifact_key")
            and step_builtin_agent_id(s) not in ("task_decomposer", "reviewer", "context_manager")
        }
        artifact_keys.discard(None)

    pipeline = state.get("pipeline") or []
    step_ids_to_clear: list[str] = []
    keys_to_clear: set[str] = set()

    for step in pipeline:
        ak = step.get("artifact_key")
        if ak and ak in artifact_keys:
            step_ids_to_clear.append(step["id"])
            keys_to_clear.add(ak)

    if not step_ids_to_clear and not report.get("passed", True):
        for step in pipeline:
            bid = step_builtin_agent_id(step)
            if bid in ("task_decomposer", "reviewer", "context_manager", "pipeline_planner"):
                continue
            if step.get("artifact_key") or bid in (
                "product_analyst",
                "architect",
                "api_designer",
                "ui_designer",
            ):
                step_ids_to_clear.append(step["id"])
                if step.get("artifact_key"):
                    keys_to_clear.add(step["artifact_key"])

    outputs = dict(state.get("agent_outputs", {}))
    artifacts = dict(state.get("artifacts", {}))

    for sid in step_ids_to_clear:
        outputs.pop(sid, None)
    for k in keys_to_clear:
        artifacts.pop(k, None)

    reviewer_steps = [s["id"] for s in pipeline if step_builtin_agent_id(s) == "reviewer"]
    for rid in reviewer_steps:
        outputs.pop(rid, None)

    return {**state, "agent_outputs": outputs, "artifacts": artifacts}


def check_l4_criteria(state: MultiAgentState) -> dict[str, bool]:
    artifacts = state.get("artifacts", {})
    review_reports = state.get("review_reports", [])
    last_report = review_reports[-1] if review_reports else {}
    tasks = state.get("tasks", [])
    pipeline = state.get("pipeline") or []
    rules = state.get("rules", {})
    l4 = rules.get("l4", {}) or {}

    required = (
        required_artifact_keys(pipeline)
        if pipeline
        else {"product_spec", "architecture_spec", "api_spec", "ui_spec"}
    )

    min_tasks = l4.get("min_tasks", 100)
    pct = l4.get("tasks_coverage_pct", 95.0)
    required_task_count = int(min_tasks * pct / 100)

    return {
        "artifacts_complete": all(k in artifacts for k in required),
        "reviewer_approved": last_report.get("passed", False),
        "no_critical_gaps": len(
            [q for q in state.get("open_questions", []) if q.get("priority") == "critical"]
        )
        == 0,
        "tasks_coverage": len(tasks) >= required_task_count,
        "saturation_done": state.get("saturation_report") is not None
        or not rules.get("rag", {}).get("enabled", True),
        "rules_compliant": last_report.get("rules_compliant", False),
    }


def _parse_artifact_key(location: str) -> str | None:
    if not location:
        return None
    loc = location.strip()
    if "/" in loc:
        loc = loc.split("/")[-1]
    loc = loc.split("#")[0]
    loc = re.sub(r"\.(md|yaml|yml|json)$", "", loc)
    return loc or None


def _find_step(state: MultiAgentState, step_id: str) -> dict[str, Any] | None:
    for step in state.get("pipeline") or []:
        if step.get("id") == step_id:
            return step
    return None


def _route_next(state: MultiAgentState) -> str:
    outputs = state.get("agent_outputs", {})
    sequence = _get_sequence(state)

    for step_id in sequence:
        if step_id == "export":
            continue
        if step_id not in outputs:
            return step_id
    return "export"


def _get_sequence(state: MultiAgentState) -> list[str]:
    if state.get("pipeline"):
        return get_routing_sequence(state)
    spec_level = state["spec_level"]
    return AGENT_SEQUENCE.get(spec_level, AGENT_SEQUENCE["L2"])


def _skip_to_next(
    state: MultiAgentState,
    stuck_agent: str | None = None,
    loop_limit: int = ANTI_LOOP_LIMIT,
) -> str:
    sequence = _get_sequence(state)
    stuck = stuck_agent or state.get("current_agent", "supervisor")
    outputs = set(state.get("agent_outputs", {}).keys())
    call_counts = state.get("agent_call_counts", {})

    for step_id in sequence:
        if step_id == "export":
            continue
        if (
            step_id not in outputs
            and call_counts.get(step_id, 0) < loop_limit
            and step_id != stuck
        ):
            return step_id
    return "export"


def _routing_reason(state: MultiAgentState, next_agent: str) -> str:
    step = _find_step(state, next_agent)
    if step:
        return f"{step.get('name', next_agent)} pending"
    if next_agent == "reviewer":
        return "All generators complete; starting quality review"
    if next_agent == "export":
        return "All agents done or time limit reached"
    return f"Routing to {next_agent}"
