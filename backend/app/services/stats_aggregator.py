"""Aggregate all-time statistics from session_metrics table."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from app.db.connection import get_db
from app.services.stats_collector import collect_and_persist_metrics

logger = structlog.get_logger(__name__)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _parse_day(iso_ts: str) -> str:
    return iso_ts[:10] if iso_ts else "unknown"


def _summary_from_row(row: dict) -> dict[str, Any]:
    metrics = json.loads(row["metrics_json"])
    scores = metrics.get("scores") or {}
    return {
        "session_id": row["session_id"],
        "status": row["status"],
        "spec_level": row["spec_level"],
        "completed_at": row["completed_at"],
        "duration_sec": row["duration_sec"],
        "quality_score": row["quality_score"],
        "project_name": metrics.get("project_name"),
        "output_slug": metrics.get("output_slug"),
        "artifacts_count": metrics.get("artifacts_count", 0),
        "tasks_total": metrics.get("tasks_total", 0),
        "errors_count": metrics.get("errors_count", 0),
        "efficiency_score": scores.get("efficiency_score", 0.0),
        "reliability_score": scores.get("reliability_score", 0.0),
    }


async def _load_all_metrics_rows() -> list[dict]:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT * FROM session_metrics ORDER BY completed_at DESC"
        )
        rows = await cursor.fetchall()
    return [dict(r) for r in rows]


async def rebuild_global_stats() -> dict[str, Any]:
    """Recompute global_stats singleton from session_metrics."""
    rows = await _load_all_metrics_rows()
    stats = _aggregate_rows(rows)

    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO global_stats (id, updated_at, stats_json)
            VALUES (1, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                updated_at = excluded.updated_at,
                stats_json = excluded.stats_json
            """,
            (_now(), json.dumps(stats, ensure_ascii=False)),
        )
        await db.commit()

    return stats


def _aggregate_rows(rows: list[dict]) -> dict[str, Any]:
    if not rows:
        return {
            "updated_at": _now(),
            "totals": {
                "sessions": 0,
                "completed": 0,
                "partial": 0,
                "failed": 0,
                "artifacts": 0,
                "tasks": 0,
                "errors": 0,
                "fallbacks": 0,
            },
            "rates": {
                "success_rate": 0.0,
                "partial_rate": 0.0,
                "avg_quality_score": 0.0,
                "avg_efficiency_score": 0.0,
                "avg_reliability_score": 0.0,
            },
            "by_spec_level": {},
            "agent_leaderboard": [],
            "trends": {"sessions_by_day": [], "avg_duration_by_day": []},
            "reliability": {
                "circuit_breaker_opens": 0,
                "agent_timeouts": 0,
                "session_stuck_events": 0,
                "budget_warnings": 0,
                "stuck_sessions": 0,
            },
            "infrastructure": {
                "avg_cpu_peak": 0.0,
                "avg_ram_peak": 0.0,
                "avg_gpu_mem_peak": 0.0,
            },
            "recent_sessions": [],
        }

    totals = {
        "sessions": len(rows),
        "completed": 0,
        "partial": 0,
        "failed": 0,
        "artifacts": 0,
        "tasks": 0,
        "errors": 0,
        "fallbacks": 0,
    }
    quality_scores: list[float] = []
    efficiency_scores: list[float] = []
    reliability_scores: list[float] = []

    by_spec: dict[str, dict] = defaultdict(
        lambda: {
            "count": 0,
            "durations": [],
            "tasks": [],
            "quality": [],
            "completed": 0,
        }
    )

    agent_calls: dict[str, int] = defaultdict(int)
    agent_durations: dict[str, list[int]] = defaultdict(list)
    agent_failures: dict[str, int] = defaultdict(int)

    reliability = {
        "circuit_breaker_opens": 0,
        "agent_timeouts": 0,
        "session_stuck_events": 0,
        "budget_warnings": 0,
        "stuck_sessions": 0,
    }

    cpu_peaks: list[float] = []
    ram_peaks: list[float] = []
    gpu_peaks: list[float] = []

    sessions_by_day: dict[str, int] = defaultdict(int)
    duration_by_day: dict[str, list[float]] = defaultdict(list)

    cutoff_90 = (datetime.now(UTC) - timedelta(days=90)).date().isoformat()

    for row in rows:
        m = json.loads(row["metrics_json"])
        status = row["status"]
        spec = row["spec_level"]

        if status == "completed":
            totals["completed"] += 1
        elif status in ("completed_partial", "degraded"):
            totals["partial"] += 1
        elif status == "failed":
            totals["failed"] += 1

        totals["artifacts"] += m.get("artifacts_count", 0)
        totals["tasks"] += m.get("tasks_total", 0)
        totals["errors"] += m.get("errors_count", 0)
        totals["fallbacks"] += m.get("fallbacks_count", 0)

        quality_scores.append(row["quality_score"])
        scores = m.get("scores") or {}
        efficiency_scores.append(scores.get("efficiency_score", 0))
        reliability_scores.append(scores.get("reliability_score", 0))

        by_spec[spec]["count"] += 1
        by_spec[spec]["durations"].append(row["duration_sec"])
        by_spec[spec]["tasks"].append(m.get("tasks_total", 0))
        by_spec[spec]["quality"].append(row["quality_score"])
        if status == "completed":
            by_spec[spec]["completed"] += 1

        for agent, count in (m.get("agent_calls") or {}).items():
            agent_calls[agent] += count
        for agent, dur in (m.get("agent_durations_ms") or {}).items():
            agent_durations[agent].append(dur)

        for agent, count in (m.get("errors_by_agent") or {}).items():
            agent_failures[agent] += count

        reliability["circuit_breaker_opens"] += m.get("circuit_breaker_opens", 0)
        reliability["agent_timeouts"] += m.get("agent_timeouts", 0)
        reliability["session_stuck_events"] += m.get("session_stuck_events", 0)
        reliability["budget_warnings"] += m.get("budget_warnings_count", 0)
        if m.get("session_stuck_events", 0) > 0:
            reliability["stuck_sessions"] += 1

        if m.get("cpu_peak"):
            cpu_peaks.append(m["cpu_peak"])
        if m.get("ram_peak"):
            ram_peaks.append(m["ram_peak"])
        if m.get("gpu_mem_peak"):
            gpu_peaks.append(m["gpu_mem_peak"])

        day = _parse_day(row["completed_at"])
        if day >= cutoff_90:
            sessions_by_day[day] += 1
            duration_by_day[day].append(row["duration_sec"])

    n = totals["sessions"]
    rates = {
        "success_rate": round(totals["completed"] / n * 100, 1) if n else 0.0,
        "partial_rate": round(totals["partial"] / n * 100, 1) if n else 0.0,
        "avg_quality_score": round(sum(quality_scores) / n, 1) if n else 0.0,
        "avg_efficiency_score": round(sum(efficiency_scores) / n, 1) if n else 0.0,
        "avg_reliability_score": round(sum(reliability_scores) / n, 1) if n else 0.0,
    }

    by_spec_level = {}
    for spec, data in sorted(by_spec.items()):
        c = data["count"]
        by_spec_level[spec] = {
            "count": c,
            "completed": data["completed"],
            "avg_duration_sec": round(sum(data["durations"]) / c, 1) if c else 0,
            "avg_tasks": round(sum(data["tasks"]) / c, 1) if c else 0,
            "avg_quality": round(sum(data["quality"]) / c, 1) if c else 0,
        }

    leaderboard = []
    all_agents = set(agent_calls) | set(agent_durations) | set(agent_failures)
    for agent in sorted(all_agents):
        calls = agent_calls.get(agent, 0)
        durs = agent_durations.get(agent, [])
        failures = agent_failures.get(agent, 0)
        avg_ms = round(sum(durs) / len(durs)) if durs else 0
        failure_rate = round(failures / calls * 100, 1) if calls else 0.0
        leaderboard.append(
            {
                "agent_id": agent,
                "total_calls": calls,
                "avg_duration_ms": avg_ms,
                "failure_rate_pct": failure_rate,
                "failures": failures,
            }
        )
    leaderboard.sort(key=lambda x: x["total_calls"], reverse=True)

    sorted_days = sorted(sessions_by_day.keys())
    trends = {
        "sessions_by_day": [
            {"date": d, "count": sessions_by_day[d]} for d in sorted_days
        ],
        "avg_duration_by_day": [
            {
                "date": d,
                "avg_duration_sec": round(sum(duration_by_day[d]) / len(duration_by_day[d]), 1),
            }
            for d in sorted_days
            if duration_by_day[d]
        ],
    }

    infrastructure = {
        "avg_cpu_peak": round(sum(cpu_peaks) / len(cpu_peaks), 1) if cpu_peaks else 0.0,
        "avg_ram_peak": round(sum(ram_peaks) / len(ram_peaks), 1) if ram_peaks else 0.0,
        "avg_gpu_mem_peak": round(sum(gpu_peaks) / len(gpu_peaks), 1) if gpu_peaks else 0.0,
    }

    recent_sessions = [_summary_from_row(r) for r in rows[:10]]

    return {
        "updated_at": _now(),
        "totals": totals,
        "rates": rates,
        "by_spec_level": by_spec_level,
        "agent_leaderboard": leaderboard,
        "trends": trends,
        "reliability": reliability,
        "infrastructure": infrastructure,
        "recent_sessions": recent_sessions,
    }


async def get_global_stats() -> dict[str, Any]:
    async with get_db() as db:
        cursor = await db.execute("SELECT stats_json FROM global_stats WHERE id = 1")
        row = await cursor.fetchone()
    if row is None:
        return await rebuild_global_stats()
    return json.loads(row["stats_json"])


async def list_session_metrics(
    *,
    limit: int = 50,
    offset: int = 0,
    spec_level: str | None = None,
) -> tuple[list[dict], int]:
    async with get_db() as db:
        if spec_level:
            count_cursor = await db.execute(
                "SELECT COUNT(*) FROM session_metrics WHERE spec_level = ?",
                (spec_level,),
            )
            total = (await count_cursor.fetchone())[0]
            cursor = await db.execute(
                "SELECT * FROM session_metrics WHERE spec_level = ? "
                "ORDER BY completed_at DESC LIMIT ? OFFSET ?",
                (spec_level, limit, offset),
            )
        else:
            count_cursor = await db.execute("SELECT COUNT(*) FROM session_metrics")
            total = (await count_cursor.fetchone())[0]
            cursor = await db.execute(
                "SELECT * FROM session_metrics ORDER BY completed_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            )
        rows = await cursor.fetchall()

    summaries = [_summary_from_row(dict(r)) for r in rows]
    return summaries, total


async def get_session_metrics_detail(session_id: str) -> dict | None:
    async with get_db() as db:
        cursor = await db.execute(
            "SELECT metrics_json FROM session_metrics WHERE session_id = ?",
            (session_id,),
        )
        row = await cursor.fetchone()
    if row is None:
        return None
    return json.loads(row["metrics_json"])


async def backfill_all_sessions(*, force: bool = False) -> dict[str, int]:
    """Backfill session_metrics for all sessions missing metrics."""
    async with get_db() as db:
        cursor = await db.execute("SELECT id, status FROM sessions ORDER BY created_at")
        sessions = await cursor.fetchall()

    processed = 0
    skipped = 0
    errors = 0

    terminal_statuses = {
        "completed",
        "completed_partial",
        "degraded",
        "failed",
        "cancelled",
    }

    for row in sessions:
        session_id = row["id"]
        status = row["status"]

        if status not in terminal_statuses and status != "running":
            if status == "pending":
                skipped += 1
                continue

        async with get_db() as db:
            existing = await db.execute(
                "SELECT 1 FROM session_metrics WHERE session_id = ?",
                (session_id,),
            )
            if await existing.fetchone() and not force:
                skipped += 1
                continue

        try:
            await collect_and_persist_metrics(session_id, state=None)
            processed += 1
        except Exception:
            logger.exception("backfill_failed", session_id=session_id)
            errors += 1

    await rebuild_global_stats()
    return {"processed": processed, "skipped": skipped, "errors": errors}


async def needs_startup_rebuild() -> bool:
    async with get_db() as db:
        gs = await db.execute("SELECT 1 FROM global_stats WHERE id = 1")
        if await gs.fetchone():
            return False
        sm = await db.execute("SELECT 1 FROM session_metrics LIMIT 1")
        if await sm.fetchone():
            return True
        sessions = await db.execute(
            "SELECT 1 FROM sessions WHERE status IN "
            "('completed','completed_partial','degraded','failed') LIMIT 1"
        )
        return await sessions.fetchone() is not None
