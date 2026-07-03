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
    insert_pipeline_steps_before_reviewer,
    required_artifact_keys,
    step_builtin_agent_id,
)
from app.agent.agents.pipeline_planner import plan_pipeline_delta, resolve_domain
from app.agent.state import MultiAgentState
from app.services.artifact_store import artifact_exists
from app.services.log_bus import log_bus
from app.services.session_control import reset_task_decomposer_steps

logger = structlog.get_logger(__name__)

ANTI_LOOP_LIMIT = 5
ANTI_LOOP_LIMIT_L4 = 15
MAX_REVIEW_CYCLES_DEFAULT = 10
PATCH_UNCHANGED_LIMIT_DEFAULT = 2
REVIEW_PLATEAU_WINDOW_DEFAULT = 3


def patch_unchanged_limit(state: MultiAgentState) -> int:
    return int(
        state.get("rules", {})
        .get("resilience", {})
        .get("patch_unchanged_limit", PATCH_UNCHANGED_LIMIT_DEFAULT)
    )


def review_plateau_window(state: MultiAgentState) -> int:
    return int(
        state.get("rules", {})
        .get("resilience", {})
        .get("review_plateau_window", REVIEW_PLATEAU_WINDOW_DEFAULT)
    )


def is_artifact_patch_exhausted(state: MultiAgentState, artifact_key: str) -> bool:
    counts = state.get("patch_unchanged_counts") or {}
    return counts.get(artifact_key, 0) >= patch_unchanged_limit(state)


def update_patch_unchanged_counts(
    state: MultiAgentState, artifact_key: str, mode: str
) -> dict[str, int]:
    counts = dict(state.get("patch_unchanged_counts") or {})
    if mode in ("patch", "generate"):
        counts.pop(artifact_key, None)
    elif mode == "unchanged":
        counts[artifact_key] = counts.get(artifact_key, 0) + 1
    return counts


def artifact_keys_from_report(report: dict[str, Any]) -> set[str]:
    keys: set[str] = set()
    for issue in report.get("issues", []):
        key = _parse_artifact_key(issue.get("location", ""))
        if key:
            keys.add(key)
    return keys


def review_confidence_plateau(
    reports: list[dict[str, Any]], window: int = REVIEW_PLATEAU_WINDOW_DEFAULT
) -> bool:
    if len(reports) < window:
        return False
    recent = reports[-window:]
    confidences = [r.get("confidence") for r in recent]
    if len(set(confidences)) != 1:
        return False
    return not recent[-1].get("passed", False)


def review_issues_plateau(
    reports: list[dict[str, Any]], window: int = REVIEW_PLATEAU_WINDOW_DEFAULT
) -> bool:
    """True when the last N reviews repeat the same issue descriptions."""
    if len(reports) < window:
        return False
    recent = reports[-window:]
    if any(r.get("passed") for r in recent):
        return False

    def _issue_fingerprint(report: dict[str, Any]) -> frozenset[str]:
        return frozenset(
            issue.get("description", "").strip().lower()
            for issue in report.get("issues", [])
            if issue.get("description")
        )

    fingerprints = [_issue_fingerprint(r) for r in recent]
    if not fingerprints[0]:
        return False
    return len({fp for fp in fingerprints}) == 1


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


async def handle_l4_post_review(
    state: MultiAgentState,
    llm_provider: Any | None = None,
) -> dict[str, Any]:
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
    until_confident = state["rules"].get("l4", {}).get("until_confident", True)
    confident_enough = passed and confidence >= min_confidence

    if all_met and confident_enough:
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
                "message": f"L4 criteria not met but max review cycles ({max_review}) reached. Exporting partial.",
            },
        )
        return {"current_agent": "export", "status": "degraded"}

    if until_confident and not confident_enough:
        plateau_window = review_plateau_window(state)
        if review_confidence_plateau(review_reports, plateau_window) or review_issues_plateau(
            review_reports, plateau_window
        ):
            await log_bus.emit(
                session_id,
                "log_entry",
                {
                    "level": "warn",
                    "agent_id": "supervisor",
                    "message": (
                        f"Review plateau ({confidence:.2f} for {plateau_window} cycles, "
                        "repeated issues). Exporting partial with gaps.md."
                    ),
                },
            )
            return {
                **state,
                "current_agent": "export",
                "status": "degraded",
                "_review_plateau": True,
            }

        flagged = artifact_keys_from_report(last_report)
        if flagged and all(is_artifact_patch_exhausted(state, k) for k in flagged):
            await log_bus.emit(
                session_id,
                "log_entry",
                {
                    "level": "warn",
                    "agent_id": "supervisor",
                    "message": "Patch exhausted for all flagged artifacts. Exporting partial.",
                },
            )
            return {"current_agent": "export", "status": "degraded"}

        replan_update = await _try_pipeline_replan(state, last_report, llm_provider, criteria)
        if replan_update:
            return replan_update

        updated = apply_refinement(state, last_report, criteria)
    elif not criteria.get("tasks_coverage"):
        updated = reset_task_decomposer_steps(state)
    else:
        updated = apply_refinement(state, last_report, criteria)

    updated = ensure_task_coverage(updated)

    issue_count = len(last_report.get("issues", []))
    artifact_count = len(updated.get("refinement_issues") or {})
    await log_bus.emit(
        session_id,
        "log_entry",
        {
            "level": "info",
            "agent_id": "supervisor",
            "message": (
                f"L4 refinement cycle #{updated.get('review_cycles', 0)}: "
                f"batch patch {issue_count} issue(s) across {artifact_count} artifact(s) "
                f"(confidence={confidence:.2f}, need {min_confidence:.2f})"
            ),
        },
    )
    await log_bus.emit(
        session_id,
        "refinement_cycle",
        {
            "cycle": updated.get("review_cycles", 0),
            "confidence": confidence,
            "min_confidence": min_confidence,
            "criteria": criteria,
        },
    )
    return {**updated, "current_agent": "supervisor"}


async def _try_pipeline_replan(
    state: MultiAgentState,
    last_report: dict[str, Any],
    llm_provider: Any | None,
    criteria: dict[str, bool],
) -> dict[str, Any] | None:
    """Extend pipeline with new steps when reviewer finds gaps and replan budget remains."""
    if llm_provider is None:
        return None

    pipeline_cfg = state.get("rules", {}).get("pipeline", {}) or {}
    max_replan = int(pipeline_cfg.get("max_replan_cycles", 2))
    replan_cycles = int(state.get("pipeline_replan_cycles", 0))
    if replan_cycles >= max_replan:
        return None

    passed = last_report.get("passed", False)
    confidence = last_report.get("confidence", 0)
    min_confidence = state["rules"].get("l4", {}).get("completion_confidence", 0.85)
    has_critical = any(
        i.get("severity") in ("critical", "high") for i in last_report.get("issues", [])
    )
    from app.agent.spec_maturity import is_production_maturity, resolve_spec_maturity

    maturity = resolve_spec_maturity(state.get("rules", {}), state.get("spec_level", "L2"))
    prod_issue = is_production_maturity(maturity) and any(
        i.get("severity") == "critical"
        or "mvp" in i.get("description", "").lower()
        or "prototype" in i.get("description", "").lower()
        for i in last_report.get("issues", [])
    )
    needs_replan = (not passed or confidence < min_confidence or not criteria.get("artifacts_complete")) and (
        has_critical or not criteria.get("artifacts_complete") or prod_issue
    )
    if not needs_replan:
        return None

    new_steps, reasoning = await plan_pipeline_delta(state, llm_provider, last_report)
    if not new_steps:
        return None

    session_id = state["session_id"]
    pipeline = insert_pipeline_steps_before_reviewer(state.get("pipeline") or [], new_steps)
    outputs = dict(state.get("agent_outputs", {}))
    reviewer_steps = [s["id"] for s in pipeline if step_builtin_agent_id(s) == "reviewer"]
    for rid in reviewer_steps:
        outputs.pop(rid, None)

    await log_bus.emit(
        session_id,
        "pipeline_extended",
        {
            "added_steps": [s.get("id") for s in new_steps],
            "reasoning": reasoning,
            "replan_cycle": replan_cycles + 1,
        },
    )
    await log_bus.emit(
        session_id,
        "log_entry",
        {
            "level": "info",
            "agent_id": "supervisor",
            "message": (
                f"Pipeline extended with {len(new_steps)} step(s) after reviewer gaps "
                f"(replan {replan_cycles + 1}/{max_replan})"
            ),
        },
    )

    from app.services.session import save_pipeline

    await save_pipeline(session_id, pipeline, f"{state.get('pipeline_reasoning', '')}\n\nDelta: {reasoning}")

    return {
        **state,
        "pipeline": pipeline,
        "agent_outputs": outputs,
        "pipeline_replan_cycles": replan_cycles + 1,
        "pipeline_version": int(state.get("pipeline_version", 1)) + 1,
        "pipeline_reasoning": f"{state.get('pipeline_reasoning', '')}\n\nDelta: {reasoning}",
        "refinement_pending": False,
        "refinement_issues": {},
        "current_agent": "supervisor",
        "review_cycles": state.get("review_cycles", 0),
    }


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
        if len(tasks) < required:
            outputs = state.get("agent_outputs", {})
            pending_task_steps = _pending_task_step_ids(pipeline, outputs)
            if pending_task_steps:
                # Mid-cycle: do not wipe progress after each completed batch.
                return state
            retries = state.get("_task_coverage_retries", 0)
            if retries >= 1:
                # One full re-run already attempted; proceed to reviewer/export.
                return state
            return {
                **reset_task_decomposer_steps(state),
                "_task_coverage_retries": retries + 1,
            }
        return state

    # Only add batches when all existing task steps are complete
    outputs = state.get("agent_outputs", {})
    pending_task_steps = _pending_task_step_ids(pipeline, outputs)
    if pending_task_steps:
        return state

    batch_num = batch_count + 1
    tasks_per_batch = l4.get("tasks_per_batch", 25)
    domain = resolve_domain(state)
    pipeline = append_extra_task_batch(
        pipeline,
        batch_num,
        tasks_per_batch,
        f"Generate additional work-package tasks to reach at least {required} total. Avoid duplicates.",
        domain=domain,
    )
    return {**state, "pipeline": pipeline}


def _pending_task_step_ids(
    pipeline: list[dict[str, Any]], outputs: dict[str, Any]
) -> list[str]:
    return [
        s["id"]
        for s in pipeline
        if step_builtin_agent_id(s) == "task_decomposer"
        and not _step_done(outputs, s["id"])
    ]


def _step_done(outputs: dict[str, Any], step_id: str) -> bool:
    val = outputs.get(step_id)
    if val is None:
        return False
    if val == "failed":
        return False
    return True


def _group_issues_by_artifact(issues: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for issue in issues:
        key = _parse_artifact_key(issue.get("location", ""))
        if key:
            grouped.setdefault(key, []).append(issue)
    return grouped


def apply_refinement(
    state: MultiAgentState,
    report: dict[str, Any],
    criteria: dict[str, bool] | None = None,
) -> MultiAgentState:
    """Queue batch patch refinement — one fixer agent patches all flagged artifacts."""
    criteria = criteria or {}
    issues = report.get("issues", [])
    grouped = _group_issues_by_artifact(issues)
    artifact_keys: set[str] = set(grouped.keys())

    pipeline = state.get("pipeline") or []

    if not artifact_keys and not criteria.get("tasks_coverage", True):
        return state

    if not artifact_keys and not report.get("passed", True):
        artifact_keys = {
            s.get("artifact_key")
            for s in pipeline
            if s.get("artifact_key")
            and step_builtin_agent_id(s) not in ("task_decomposer", "reviewer", "context_manager")
        }
        artifact_keys.discard(None)
        for key in artifact_keys:
            grouped.setdefault(key, issues)

    refinement_issues = dict(state.get("refinement_issues") or {})
    for key in artifact_keys:
        if key in grouped:
            refinement_issues[key] = grouped[key]
        else:
            refinement_issues[key] = [
                {
                    "severity": "medium",
                    "description": report.get("summary", "Improve quality per reviewer feedback"),
                    "location": f"{key}#general",
                }
            ]

    outputs = dict(state.get("agent_outputs", {}))
    outputs.pop("refinement_fixer", None)
    reviewer_steps = [s["id"] for s in pipeline if step_builtin_agent_id(s) == "reviewer"]
    for rid in reviewer_steps:
        outputs.pop(rid, None)

    return {
        **state,
        "agent_outputs": outputs,
        "refinement_issues": refinement_issues,
        "refinement_pending": bool(artifact_keys),
    }


def check_l4_criteria(state: MultiAgentState) -> dict[str, bool]:
    artifacts = state.get("artifacts", {})
    review_reports = state.get("review_reports", [])
    last_report = review_reports[-1] if review_reports else {}
    tasks = state.get("tasks", [])
    pipeline = state.get("pipeline") or []
    rules = state.get("rules", {})
    l4 = rules.get("l4", {}) or {}

    required = required_artifact_keys(pipeline) if pipeline else set()

    min_tasks = l4.get("min_tasks", 100)
    pct = l4.get("tasks_coverage_pct", 95.0)
    required_task_count = int(min_tasks * pct / 100)
    min_confidence = l4.get("completion_confidence", 0.85)

    return {
        "artifacts_complete": all(
            k in artifacts or artifact_exists(state["session_id"], k) for k in required
        ),
        "reviewer_approved": last_report.get("passed", False)
        and last_report.get("confidence", 0) >= min_confidence,
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
    if state.get("refinement_pending") and not _step_done(outputs, "refinement_fixer"):
        return "refinement_fixer"

    sequence = _get_sequence(state)

    for step_id in sequence:
        if step_id == "export":
            continue
        if not _step_done(outputs, step_id):
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
    outputs = state.get("agent_outputs", {})
    call_counts = state.get("agent_call_counts", {})

    for step_id in sequence:
        if step_id == "export":
            continue
        if (
            not _step_done(outputs, step_id)
            and call_counts.get(step_id, 0) < loop_limit
            and step_id != stuck
        ):
            return step_id
    return "export"


def _routing_reason(state: MultiAgentState, next_agent: str) -> str:
    if next_agent == "refinement_fixer":
        issues = state.get("refinement_issues") or {}
        n_issues = sum(len(v) for v in issues.values())
        return f"Batch patch refinement ({len(issues)} artifacts, {n_issues} issues)"
    step = _find_step(state, next_agent)
    if step:
        return f"{step.get('name', next_agent)} pending"
    if next_agent == "reviewer":
        return "All generators complete; starting quality review"
    if next_agent == "export":
        return "All agents done or time limit reached"
    return f"Routing to {next_agent}"
