"""Supervisor agent — routing, quality gates, time budget, L4 completion criteria."""

from __future__ import annotations

import time
from typing import Any

import structlog

from app.agent.pipeline_utils import AGENT_SEQUENCE, get_routing_sequence, required_artifact_keys
from app.agent.state import MultiAgentState
from app.services.log_bus import log_bus

logger = structlog.get_logger(__name__)

ANTI_LOOP_LIMIT = 5
MAX_REVIEW_CYCLES_DEFAULT = 10


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
    next_agent = _route_next(state)
    if next_agent != "export" and call_counts.get(next_agent, 0) >= ANTI_LOOP_LIMIT:
        logger.warning("anti_loop_triggered", agent=next_agent, session_id=session_id)
        await log_bus.emit(
            session_id,
            "log_entry",
            {
                "level": "warn",
                "agent_id": "supervisor",
                "message": f"Anti-loop: {next_agent} called {ANTI_LOOP_LIMIT}+ times. Skipping.",
            },
        )
        skip_agent = _skip_to_next(state, stuck_agent=next_agent)
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
        return {**state, "current_agent": "export"}

    current = state.get("current_agent", "supervisor")
    if spec_level == "L4" and current == "reviewer":
        review_reports = state.get("review_reports", [])
        if review_reports:
            last_report = review_reports[-1]
            confidence = last_report.get("confidence", 0)
            passed = last_report.get("passed", False)
            criteria = _check_l4_criteria(state)
            all_met = all(criteria.values())
            await log_bus.emit(
                session_id, "completion_check", {"criteria": criteria, "all_met": all_met}
            )
            if (
                all_met
                and passed
                and confidence >= state["rules"].get("l4", {}).get("completion_confidence", 0.85)
            ):
                return {**state, "current_agent": "export"}

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


def _skip_to_next(state: MultiAgentState, stuck_agent: str | None = None) -> str:
    sequence = _get_sequence(state)
    stuck = stuck_agent or state.get("current_agent", "supervisor")
    outputs = set(state.get("agent_outputs", {}).keys())
    call_counts = state.get("agent_call_counts", {})

    for step_id in sequence:
        if step_id == "export":
            continue
        if (
            step_id not in outputs
            and call_counts.get(step_id, 0) < ANTI_LOOP_LIMIT
            and step_id != stuck
        ):
            return step_id
    return "export"


def _routing_reason(state: MultiAgentState, next_agent: str) -> str:
    outputs = state.get("agent_outputs", {})
    step = _find_step(state, next_agent)
    if step:
        return f"{step.get('name', next_agent)} pending"
    if next_agent == "reviewer":
        return "All generators complete; starting quality review"
    if next_agent == "export":
        return "All agents done or time limit reached"
    if next_agent not in outputs:
        return f"{next_agent} output missing; dispatching"
    return f"Routing to {next_agent}"


def _check_l4_criteria(state: MultiAgentState) -> dict[str, bool]:
    artifacts = state.get("artifacts", {})
    review_reports = state.get("review_reports", [])
    last_report = review_reports[-1] if review_reports else {}
    tasks = state.get("tasks", [])
    pipeline = state.get("pipeline") or []
    required = (
        required_artifact_keys(pipeline)
        if pipeline
        else {"product_spec", "architecture_spec", "api_spec", "ui_spec"}
    )

    return {
        "artifacts_complete": all(k in artifacts for k in required),
        "reviewer_approved": last_report.get("passed", False),
        "no_critical_gaps": len(
            [q for q in state.get("open_questions", []) if q.get("priority") == "critical"]
        )
        == 0,
        "tasks_coverage": len(tasks) > 0,
        "saturation_done": state.get("saturation_report") is not None,
        "rules_compliant": last_report.get("rules_compliant", False),
    }
