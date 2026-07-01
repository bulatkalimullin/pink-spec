"""Collect per-session metrics from state, logs, and infrastructure accumulator."""

from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from app.config import get_settings
from app.db.connection import get_db
from app.services.log_bus import log_bus
from app.services.session_metrics_accumulator import session_metrics_accumulator

logger = structlog.get_logger(__name__)

_TIME_BUDGETS = {"L1": 300, "L2": 900, "L3": 1800, "L4": None}
_TASK_BASELINES = {"L1": 5, "L2": 20, "L3": 60, "L4": 100}
_DURATION_BASELINES = {"L1": 300, "L2": 900, "L3": 1800, "L4": 3600}


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _count_phases(tasks: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for t in tasks:
        counts[t.get("phase", "unknown")] += 1
    return dict(counts)


def _count_priorities(tasks: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for t in tasks:
        counts[t.get("priority", "medium")] += 1
    return dict(counts)


def _errors_by_agent(errors: list[str]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for e in errors:
        agent = e.split(":")[0].strip() if ":" in e else "unknown"
        counts[agent] += 1
    return dict(counts)


def _fallbacks_by_layer(fallbacks: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for fb in fallbacks:
        counts[fb.get("layer", "unknown")] += 1
    return dict(counts)


def _analyze_logs(logs: list[dict]) -> dict[str, Any]:
    events_by_type: dict[str, int] = defaultdict(int)
    log_errors_count = 0
    circuit_breaker_opens = 0
    agent_timeouts = 0
    session_stuck_events = 0
    budget_warnings_count = 0
    l4_criteria: dict[str, bool] = {}
    l4_all_met = False
    l4_final_confidence: float | None = None
    agent_durations_from_logs: dict[str, list[int]] = defaultdict(list)

    for entry in logs:
        etype = entry.get("type", "")
        payload = entry.get("payload") or {}
        events_by_type[etype] += 1

        if etype == "log_entry" and payload.get("level") == "error":
            log_errors_count += 1
        elif etype == "circuit_breaker_open":
            circuit_breaker_opens += 1
        elif etype == "agent_timeout":
            agent_timeouts += 1
        elif etype == "session_stuck":
            session_stuck_events += 1
        elif etype == "budget_warning":
            budget_warnings_count += 1
        elif etype == "completion_check":
            l4_criteria = payload.get("criteria", {})
            l4_all_met = payload.get("all_met", False)
        elif etype == "refinement_cycle":
            l4_final_confidence = payload.get("confidence")
        elif etype == "agent_completed":
            aid = payload.get("agent_id")
            dur = payload.get("duration_ms")
            if aid and dur is not None:
                agent_durations_from_logs[aid].append(int(dur))

    return {
        "events_total": len(logs),
        "events_by_type": dict(events_by_type),
        "log_errors_count": log_errors_count,
        "circuit_breaker_opens": circuit_breaker_opens,
        "agent_timeouts": agent_timeouts,
        "session_stuck_events": session_stuck_events,
        "budget_warnings_count": budget_warnings_count,
        "l4_criteria": l4_criteria,
        "l4_all_met": l4_all_met,
        "l4_final_confidence": l4_final_confidence,
        "agent_durations_from_logs": {
            k: sum(v) // len(v) for k, v in agent_durations_from_logs.items()
        },
    }


def _compute_scores(
    *,
    status: str,
    spec_level: str,
    is_partial: bool,
    artifacts_count: int,
    tasks_total: int,
    duration_sec: float,
    assumptions_count: int,
    errors_count: int,
    fallbacks_count: int,
    has_gaps_file: bool,
    l4_all_met: bool,
    review_reports_count: int,
    circuit_breaker_opens: int,
    agent_timeouts: int,
    session_stuck_events: int,
) -> dict[str, float]:
    quality = 0.0
    if status == "completed":
        quality += 40.0
    elif status in ("completed_partial", "degraded"):
        quality += 20.0
    elif status == "failed":
        quality += 0.0
    else:
        quality += 10.0

    if l4_all_met:
        quality += 20.0
    elif review_reports_count > 0 and status == "completed":
        quality += 10.0

    if assumptions_count <= 5:
        quality += 10.0
    elif assumptions_count <= 15:
        quality += 5.0

    if not has_gaps_file:
        quality += 10.0

    if artifacts_count >= 3:
        quality += 10.0

    quality -= min(errors_count * 5, 25)
    quality -= min(fallbacks_count * 2, 10)
    quality = max(0.0, min(100.0, quality))

    baseline_tasks = _TASK_BASELINES.get(spec_level, 20)
    baseline_duration = _DURATION_BASELINES.get(spec_level, 900)
    task_ratio = min(tasks_total / baseline_tasks, 2.0) if baseline_tasks else 0.5
    duration_ratio = (
        baseline_duration / duration_sec if duration_sec > 0 else 0.5
    )
    efficiency = (task_ratio * 50 + min(duration_ratio, 1.5) * 50) / 1.5
    efficiency = max(0.0, min(100.0, efficiency))

    reliability = 100.0
    reliability -= circuit_breaker_opens * 15
    reliability -= agent_timeouts * 10
    reliability -= session_stuck_events * 20
    reliability -= errors_count * 5
    if is_partial:
        reliability -= 10.0
    reliability = max(0.0, min(100.0, reliability))

    return {
        "quality_score": round(quality, 1),
        "efficiency_score": round(efficiency, 1),
        "reliability_score": round(reliability, 1),
    }


def build_metrics_from_state(
    state: dict[str, Any],
    logs: list[dict],
    infra: dict[str, float | int],
) -> dict[str, Any]:
    """Build full metrics dict from runtime state + logs + infra snapshot."""
    spec_level = state.get("spec_level", "L2")
    status = state.get("status", "unknown")
    artifacts = state.get("artifacts") or {}
    tasks = state.get("tasks") or []
    errors = state.get("errors") or []
    fallbacks = state.get("fallbacks_triggered") or []
    agent_calls = state.get("agent_call_counts") or {}
    agent_durations = state.get("agent_durations") or {}
    saturation = state.get("saturation_report") or {}
    rules = state.get("rules") or {}
    pipeline = state.get("pipeline") or []

    started_at = state.get("started_at") or time.time()
    duration_sec = state.get("duration_sec")
    if duration_sec is None:
        duration_sec = time.time() - started_at

    time_budget = state.get("time_budget_sec")
    if time_budget is None:
        time_budget = _TIME_BUDGETS.get(spec_level)

    budget_used_pct = None
    if time_budget and time_budget > 0:
        budget_used_pct = round(duration_sec / time_budget * 100, 1)

    artifacts_count = len([v for v in artifacts.values() if v])
    artifact_types = [k for k, v in artifacts.items() if v]
    tasks_by_phase = _count_phases(tasks)
    tasks_by_priority = _count_priorities(tasks)
    est_minutes = sum(int(t.get("estimated_minutes", 0) or 0) for t in tasks)

    slowest_agent_id = None
    avg_agent_duration_ms = 0
    if agent_durations:
        slowest_agent_id = max(agent_durations, key=agent_durations.get)
        avg_agent_duration_ms = sum(agent_durations.values()) // len(agent_durations)

    log_analysis = _analyze_logs(logs)
    if not agent_durations and log_analysis["agent_durations_from_logs"]:
        agent_durations = log_analysis["agent_durations_from_logs"]
        if agent_durations:
            slowest_agent_id = max(agent_durations, key=agent_durations.get)
            avg_agent_duration_ms = sum(agent_durations.values()) // len(agent_durations)

    rag_fallback_used = any(
        fb.get("layer", "").lower() in ("rag", "embedding", "retrieval")
        for fb in fallbacks
    )

    is_partial = status in ("completed_partial", "degraded") or bool(
        state.get("is_partial")
    )
    has_gaps_file = bool(state.get("has_gaps_file"))

    scores = _compute_scores(
        status=status,
        spec_level=spec_level,
        is_partial=is_partial,
        artifacts_count=artifacts_count,
        tasks_total=len(tasks),
        duration_sec=float(duration_sec),
        assumptions_count=len(state.get("assumptions") or []),
        errors_count=len(errors),
        fallbacks_count=len(fallbacks),
        has_gaps_file=has_gaps_file,
        l4_all_met=log_analysis["l4_all_met"],
        review_reports_count=len(state.get("review_reports") or []),
        circuit_breaker_opens=log_analysis["circuit_breaker_opens"],
        agent_timeouts=log_analysis["agent_timeouts"],
        session_stuck_events=log_analysis["session_stuck_events"],
    )

    pipeline_cfg = rules.get("pipeline") or {}

    return {
        "session_id": state.get("session_id"),
        "status": status,
        "spec_level": spec_level,
        "is_partial": is_partial,
        "duration_sec": round(float(duration_sec), 1),
        "time_budget_sec": time_budget,
        "budget_used_pct": budget_used_pct,
        "idea_length_chars": len(state.get("idea") or ""),
        "artifacts_count": artifacts_count,
        "artifact_types": artifact_types,
        "tasks_total": len(tasks),
        "tasks_by_phase": tasks_by_phase,
        "tasks_by_priority": tasks_by_priority,
        "tasks_estimated_minutes_total": est_minutes,
        "pipeline_steps_count": len(pipeline),
        "pipeline_mode": pipeline_cfg.get("mode", "auto"),
        "has_gaps_file": has_gaps_file,
        "total_agent_calls": sum(agent_calls.values()),
        "agent_calls": dict(agent_calls),
        "agent_durations_ms": dict(agent_durations),
        "slowest_agent_id": slowest_agent_id,
        "avg_agent_duration_ms": avg_agent_duration_ms,
        "review_cycles": state.get("review_cycles", 0),
        "checkpoints_count": len(state.get("checkpoints") or []),
        "recovery_actions_count": len(state.get("recovery_trace") or []),
        "assumptions_count": len(state.get("assumptions") or []),
        "decisions_count": len(state.get("decisions") or []),
        "open_questions_count": len(state.get("open_questions") or []),
        "review_reports_count": len(state.get("review_reports") or []),
        "l4_criteria": log_analysis["l4_criteria"],
        "l4_all_met": log_analysis["l4_all_met"],
        "l4_final_confidence": log_analysis["l4_final_confidence"],
        "errors_count": len(errors),
        "errors_by_agent": _errors_by_agent(errors),
        "fallbacks_count": len(fallbacks),
        "fallbacks_by_layer": _fallbacks_by_layer(fallbacks),
        "circuit_breaker_opens": log_analysis["circuit_breaker_opens"],
        "agent_timeouts": log_analysis["agent_timeouts"],
        "session_stuck_events": log_analysis["session_stuck_events"],
        "budget_warnings_count": log_analysis["budget_warnings_count"],
        "saturation_iterations": saturation.get("iterations"),
        "saturation_chunks": saturation.get("chunks"),
        "saturation_novelty": saturation.get("novelty"),
        "rag_fallback_used": rag_fallback_used,
        "events_total": log_analysis["events_total"],
        "events_by_type": log_analysis["events_by_type"],
        "log_errors_count": log_analysis["log_errors_count"],
        **infra,
        "scores": scores,
    }


def _load_manifest_from_disk(session_id: str) -> dict | None:
    path = Path(get_settings().output_path) / session_id / "manifest.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _state_from_manifest_and_session(
    session_id: str,
    session_row: dict,
    manifest: dict | None,
) -> dict[str, Any]:
    """Reconstruct partial state for backfill when runtime state is unavailable."""
    rules = session_row.get("rules") or {}
    spec_level = session_row.get("spec_level", rules.get("spec_level", "L2"))
    status = session_row.get("status", "unknown")
    manifest = manifest or session_row.get("manifest") or {}

    tasks_info = manifest.get("tasks") or {}
    tasks_count = tasks_info.get("count", 0)
    artifacts = manifest.get("artifacts") or {}

    saturation = (manifest.get("context") or {}).get("saturation") or {}
    duration_sec = manifest.get("duration_sec", 0)

    gaps_file = manifest.get("gaps_file")
    is_partial = status in ("completed_partial", "degraded") or bool(gaps_file)

    return {
        "session_id": session_id,
        "idea": session_row.get("idea", ""),
        "rules": rules,
        "spec_level": spec_level,
        "status": status,
        "started_at": time.time() - duration_sec if duration_sec else time.time(),
        "duration_sec": duration_sec,
        "time_budget_sec": _TIME_BUDGETS.get(spec_level),
        "artifacts": {k: "<backfill>" for k in artifacts},
        "tasks": [{"phase": p} for p in range(tasks_count)],
        "assumptions": manifest.get("assumptions") or [],
        "decisions": manifest.get("decisions") or [],
        "review_reports": manifest.get("review_reports") or [],
        "recovery_trace": manifest.get("recovery_trace") or [],
        "errors": manifest.get("errors") or [],
        "fallbacks_triggered": [],
        "agent_call_counts": {},
        "agent_durations": {},
        "review_cycles": 0,
        "checkpoints": [],
        "open_questions": [],
        "saturation_report": saturation,
        "pipeline": manifest.get("pipeline") or session_row.get("pipeline") or [],
        "has_gaps_file": bool(gaps_file),
        "is_partial": is_partial,
    }


async def collect_session_metrics(
    session_id: str,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Collect metrics for a session. Uses live state if provided, else backfill sources."""
    logs = await log_bus.get_log_history(session_id, from_seq=0, limit=50_000)
    infra = session_metrics_accumulator.snapshot(session_id)

    if state is None:
        from app.services.session import get_session

        session_row = await get_session(session_id)
        if session_row is None:
            raise ValueError(f"Session not found: {session_id}")
        manifest = session_row.get("manifest") or _load_manifest_from_disk(session_id)
        state = _state_from_manifest_and_session(session_id, session_row, manifest)

    metrics = build_metrics_from_state(state, logs, infra)
    return metrics


async def persist_session_metrics(
    session_id: str,
    metrics: dict[str, Any],
    *,
    completed_at: str | None = None,
) -> None:
    """Upsert session_metrics row."""
    scores = metrics.get("scores") or {}
    quality_score = scores.get("quality_score", 0.0)
    completed = completed_at or _now()

    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO session_metrics
                (session_id, status, spec_level, completed_at, duration_sec, quality_score, metrics_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                status = excluded.status,
                spec_level = excluded.spec_level,
                completed_at = excluded.completed_at,
                duration_sec = excluded.duration_sec,
                quality_score = excluded.quality_score,
                metrics_json = excluded.metrics_json
            """,
            (
                session_id,
                metrics.get("status", "unknown"),
                metrics.get("spec_level", "L2"),
                completed,
                metrics.get("duration_sec", 0),
                quality_score,
                json.dumps(metrics, ensure_ascii=False),
            ),
        )
        await db.commit()


async def collect_and_persist_metrics(
    session_id: str,
    state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Collect, persist, rebuild global cache, and clear infra accumulator."""
    try:
        metrics = await collect_session_metrics(session_id, state)
        await persist_session_metrics(session_id, metrics)
        from app.services.stats_aggregator import rebuild_global_stats

        await rebuild_global_stats()
        return metrics
    finally:
        session_metrics_accumulator.clear(session_id)
