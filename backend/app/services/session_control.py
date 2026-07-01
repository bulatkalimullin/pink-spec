"""Runtime session control — user directives and live rule overrides."""

from __future__ import annotations

from typing import Any

from app.agent.pipeline_utils import step_builtin_agent_id
from app.agent.state import MultiAgentState
from app.services.artifact_store import clear_session_output, clear_tasks, remove_artifact

_pending: dict[str, list[dict[str, Any]]] = {}
_overrides: dict[str, dict[str, Any]] = {}


def enqueue(session_id: str, directive: dict[str, Any]) -> None:
    _pending.setdefault(session_id, []).append(directive)


def pop_all(session_id: str) -> list[dict[str, Any]]:
    return _pending.pop(session_id, [])


def set_overrides(session_id: str, overrides: dict[str, Any]) -> dict[str, Any]:
    current = dict(_overrides.get(session_id, {}))
    current.update({k: v for k, v in overrides.items() if v is not None})
    _overrides[session_id] = current
    return current


def get_overrides(session_id: str) -> dict[str, Any]:
    return dict(_overrides.get(session_id, {}))


def clear_session(session_id: str) -> None:
    _pending.pop(session_id, None)
    _overrides.pop(session_id, None)


def apply_rules_overrides(rules: dict[str, Any], session_id: str) -> dict[str, Any]:
    overrides = get_overrides(session_id)
    if not overrides:
        return rules

    rules = dict(rules)
    if overrides.get("max_review_cycles") is not None:
        resilience = dict(rules.get("resilience", {}) or {})
        resilience["max_review_cycles"] = overrides["max_review_cycles"]
        rules["resilience"] = resilience
    if overrides.get("completion_confidence") is not None:
        l4 = dict(rules.get("l4", {}) or {})
        l4["completion_confidence"] = overrides["completion_confidence"]
        rules["l4"] = l4
    if overrides.get("until_confident") is not None:
        l4 = dict(rules.get("l4", {}) or {})
        l4["until_confident"] = overrides["until_confident"]
        rules["l4"] = l4
    return rules


def apply_control_directives(state: MultiAgentState, directives: list[dict[str, Any]]) -> MultiAgentState:
    """Apply queued user control actions to graph state."""
    if not directives:
        return state

    session_id = state["session_id"]
    rules = apply_rules_overrides(state.get("rules", {}), session_id)

    for directive in directives:
        action = directive.get("action")
        if action == "update_settings":
            set_overrides(session_id, directive)
            rules = apply_rules_overrides(rules, session_id)
            continue
        if action == "replan_pipeline":
            state = trigger_replan(state)
        elif action == "retry_tasks":
            state = reset_task_decomposer_steps(state)
        elif action == "retry_reviewer":
            state = clear_reviewer_outputs(state)
        elif action == "force_export":
            from app.services.session_runner import session_runner

            session_runner.request_cancel(session_id)
            return {**state, "rules": rules, "current_agent": "export", "status": "degraded"}
        elif action == "retry_agent" and directive.get("target_agent"):
            target = directive["target_agent"]
            outputs = dict(state.get("agent_outputs", {}))
            outputs.pop(target, None)
            step = next(
                (s for s in (state.get("pipeline") or []) if s.get("id") == target),
                None,
            )
            artifacts = dict(state.get("artifacts", {}))
            if step and step.get("artifact_key"):
                ak = step["artifact_key"]
                artifacts.pop(ak, None)
                remove_artifact(session_id, ak)
            from app.services.session_runner import session_runner

            session_runner.request_cancel(session_id)
            state = {**state, "agent_outputs": outputs, "artifacts": artifacts}
        elif action == "restart_from" and directive.get("target_agent"):
            target = directive["target_agent"]
            pipeline = state.get("pipeline") or []
            outputs = dict(state.get("agent_outputs", {}))
            artifacts = dict(state.get("artifacts", {}))
            clearing = False
            for step in pipeline:
                sid = step.get("id", "")
                if sid == target:
                    clearing = True
                if clearing:
                    outputs.pop(sid, None)
                    ak = step.get("artifact_key")
                    if ak:
                        artifacts.pop(ak, None)
                        remove_artifact(session_id, ak)
            from app.services.session_runner import session_runner

            session_runner.request_cancel(session_id)
            state = {
                **state,
                "agent_outputs": outputs,
                "artifacts": artifacts,
                "current_agent": "supervisor",
                "current_step": None,
            }
        elif action == "skip_agent" and directive.get("target_agent"):
            outputs = {
                **state.get("agent_outputs", {}),
                directive["target_agent"]: "skipped_by_user",
            }
            state = {**state, "agent_outputs": outputs}

    return {**state, "rules": rules}


def trigger_replan(state: MultiAgentState) -> MultiAgentState:
    """Re-run pipeline planner and regenerate specs from scratch (keep researcher)."""
    clear_session_output(state["session_id"])
    outputs = {
        k: v for k, v in state.get("agent_outputs", {}).items() if k in ("researcher",)
    }
    pipeline = [
        {
            "id": "pipeline_planner",
            "name": "Pipeline Planner",
            "executor": "builtin:pipeline_planner",
            "executor_agent": "pipeline_planner",
            "artifact_key": None,
            "required": True,
        },
    ]
    return {
        **state,
        "agent_outputs": outputs,
        "artifacts": {},
        "tasks": [],
        "pipeline": pipeline,
        "pipeline_planned": False,
        "pipeline_reasoning": "Re-planned by user request",
        "review_reports": [],
        "review_cycles": 0,
        "refinement_pending": False,
        "refinement_issues": {},
        "patch_unchanged_counts": {},
        "current_agent": "supervisor",
        "current_step": None,
    }


def reset_task_decomposer_steps(state: MultiAgentState) -> MultiAgentState:
    """Clear task decomposer step outputs so batches can run again."""
    clear_tasks(state["session_id"])
    pipeline = state.get("pipeline") or []
    outputs = dict(state.get("agent_outputs", {}))
    for step in pipeline:
        if step_builtin_agent_id(step) == "task_decomposer":
            outputs.pop(step["id"], None)
    reviewer_ids = [s["id"] for s in pipeline if step_builtin_agent_id(s) == "reviewer"]
    for rid in reviewer_ids:
        outputs.pop(rid, None)
    return {**state, "agent_outputs": outputs, "tasks": [], "current_agent": "supervisor"}


def clear_reviewer_outputs(state: MultiAgentState) -> MultiAgentState:
    pipeline = state.get("pipeline") or []
    outputs = dict(state.get("agent_outputs", {}))
    for step in pipeline:
        if step_builtin_agent_id(step) == "reviewer":
            outputs.pop(step["id"], None)
    return {**state, "agent_outputs": outputs, "current_agent": "supervisor"}
