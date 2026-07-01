"""Session progress, ETA, and stage_changed event emission."""

from __future__ import annotations

import time
from typing import Any

from app.agent.pipeline_utils import step_builtin_agent_id
from app.agent.state import MultiAgentState
from app.services.log_bus import log_bus

STAGE_LABELS_RU: dict[str, str] = {
    "ingest": "Загружаем источники",
    "saturation": "Собираем контекст",
    "context_ready": "Контекст получен",
    "planning": "Планируем пайплайн",
    "generate": "Генерируем",
    "summarize": "Сжимаем контекст",
    "validate": "Проверяем качество",
    "export": "Экспортируем",
    "done": "Готово",
    "starting": "Запускаем сессию",
}


def _pipeline_step_ids(state: MultiAgentState) -> list[str]:
    pipeline = state.get("pipeline") or []
    ids = [s["id"] for s in pipeline if s.get("id") != "export"]
    ids.append("export")
    return ids


def _completed_step_ids(state: MultiAgentState) -> set[str]:
    outputs = state.get("agent_outputs", {})
    completed: set[str] = set()
    for step_id in _pipeline_step_ids(state):
        if step_id == "export":
            continue
        if outputs.get(step_id) is not None:
            completed.add(step_id)
        elif step_id in outputs:
            completed.add(step_id)
    return completed


def _current_step_index(state: MultiAgentState, stage_id: str, agent_id: str | None) -> int:
    ids = _pipeline_step_ids(state)
    target = agent_id or stage_id
    if target in ids:
        return ids.index(target) + 1
    current = state.get("current_agent")
    if current and current in ids:
        return ids.index(current) + 1
    completed = len(_completed_step_ids(state))
    return min(completed + 1, len(ids))


def compute_progress(
    state: MultiAgentState,
    *,
    stage_id: str,
    agent_id: str | None = None,
    sub_progress: float = 0.0,
) -> int:
    """Overall session progress 0-100."""
    ids = _pipeline_step_ids(state)
    total = max(len(ids), 1)
    completed = _completed_step_ids(state)

    credit = 0.0
    for i, step_id in enumerate(ids):
        if step_id in completed:
            credit += 1.0
        elif step_id == (agent_id or state.get("current_agent")) or step_id == stage_id:
            credit += min(max(sub_progress, 0.0), 1.0)
            break
        elif i < len(completed):
            continue
        else:
            break

    if stage_id == "done":
        return 100

    return min(99, max(0, int((credit / total) * 100)))


def compute_eta(
    state: MultiAgentState,
    *,
    percent: int,
    stage_id: str,
    agent_id: str | None = None,
    saturation_iteration: int | None = None,
    saturation_max: int | None = None,
) -> int | None:
    """Estimate seconds until session completion."""
    elapsed = int(time.time() - state["started_at"])
    if percent >= 100 or stage_id == "done":
        return 0
    if percent < 10 and not state.get("agent_durations"):
        return None

    durations: dict[str, int] = state.get("agent_durations") or {}
    avg_ms = 0
    if durations:
        avg_ms = sum(durations.values()) // len(durations)
    avg_sec = max(avg_ms / 1000, 30.0)

    ids = _pipeline_step_ids(state)
    completed = _completed_step_ids(state)
    remaining_steps = [s for s in ids if s not in completed and s != "export"]
    if state.get("current_agent") and state["current_agent"] not in completed:
        if state["current_agent"] not in remaining_steps and state["current_agent"] != "export":
            remaining_steps = [state["current_agent"], *remaining_steps]

    eta = len(remaining_steps) * avg_sec
    if agent_id or state.get("current_agent"):
        eta += avg_sec * 0.5

    if stage_id == "saturation" and saturation_iteration and saturation_max:
        researcher_avg = durations.get("researcher", int(avg_ms)) / 1000
        frac = saturation_iteration / max(saturation_max, 1)
        eta = researcher_avg * (1.0 - frac) + len(remaining_steps) * avg_sec

    if percent >= 10 and (not durations or eta <= 0):
        eta = elapsed * (100 - percent) / max(percent, 1)

    eta = int(max(eta, 0))

    time_budget = state.get("time_budget_sec")
    safety_cap = state.get("safety_cap_sec", 7200)
    spec_level = state.get("spec_level", "L2")
    hard_limit = safety_cap if spec_level == "L4" else time_budget
    if hard_limit:
        remaining_budget = int(hard_limit - elapsed)
        if remaining_budget >= 0:
            eta = min(eta, remaining_budget)

    return eta


def _budget_remaining_sec(state: MultiAgentState) -> int | None:
    elapsed = time.time() - state["started_at"]
    time_budget = state.get("time_budget_sec")
    safety_cap = state.get("safety_cap_sec", 7200)
    spec_level = state.get("spec_level", "L2")
    hard_limit = safety_cap if spec_level == "L4" else time_budget
    if hard_limit:
        return max(0, int(hard_limit - elapsed))
    return None


async def emit_stage_changed(
    state: MultiAgentState,
    *,
    stage_id: str,
    label: str | None = None,
    detail: str | None = None,
    agent_id: str | None = None,
    sub_progress: float = 0.5,
    saturation_iteration: int | None = None,
    saturation_max: int | None = None,
) -> None:
    """Emit stage_changed WS event with progress and ETA."""
    session_id = state["session_id"]
    ids = _pipeline_step_ids(state)
    percent = compute_progress(
        state, stage_id=stage_id, agent_id=agent_id, sub_progress=sub_progress
    )
    elapsed_sec = int(time.time() - state["started_at"])
    eta_sec = compute_eta(
        state,
        percent=percent,
        stage_id=stage_id,
        agent_id=agent_id,
        saturation_iteration=saturation_iteration,
        saturation_max=saturation_max,
    )
    step_index = _current_step_index(state, stage_id, agent_id)

    await log_bus.emit(
        session_id,
        "stage_changed",
        {
            "stage_id": stage_id,
            "label": label or STAGE_LABELS_RU.get(stage_id, stage_id),
            "detail": detail,
            "percent": percent,
            "step_index": step_index,
            "total_steps": len(ids),
            "agent_id": agent_id,
            "elapsed_sec": elapsed_sec,
            "eta_sec": eta_sec,
            "budget_remaining_sec": _budget_remaining_sec(state),
        },
    )


def record_agent_duration(state: MultiAgentState, agent_id: str, duration_ms: int) -> dict[str, Any]:
    """Return state patch with updated agent_durations."""
    durations = dict(state.get("agent_durations") or {})
    durations[agent_id] = duration_ms
    return {"agent_durations": durations}


def generate_label_for_agent(state: MultiAgentState, agent_id: str, agent_name: str) -> str:
    """RU label for agent start."""
    step = None
    for s in state.get("pipeline") or []:
        if s.get("id") == agent_id:
            step = s
            break
    name = step.get("name") if step else agent_name
    builtin = step_builtin_agent_id(step) if step else agent_id

    if builtin == "researcher":
        return STAGE_LABELS_RU["saturation"]
    if builtin == "pipeline_planner":
        return STAGE_LABELS_RU["planning"]
    if builtin == "context_manager":
        return STAGE_LABELS_RU["summarize"]
    if builtin == "reviewer":
        return STAGE_LABELS_RU["validate"]
    if agent_id == "refinement_fixer":
        return "Патчим по review"
    if builtin == "export" or agent_id == "export":
        return STAGE_LABELS_RU["export"]
    if step and step.get("executor") == "generic":
        return f"Генерируем {name}"
    return f"Генерируем {name}"
