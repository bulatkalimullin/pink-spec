"""Statistics API — all-time metrics and backfill."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.stats import (
    GlobalStatsResponse,
    RebuildStatsResponse,
    SessionMetricsListResponse,
    SessionMetricsSummary,
)
from app.services.stats_aggregator import (
    backfill_all_sessions,
    get_global_stats,
    get_session_metrics_detail,
    list_session_metrics,
)

router = APIRouter(prefix="/api/v1/stats", tags=["stats"])


@router.get("/global", response_model=GlobalStatsResponse)
async def global_stats():
    """Cached all-time aggregates."""
    data = await get_global_stats()
    return GlobalStatsResponse(**data)


@router.get("/sessions", response_model=SessionMetricsListResponse)
async def session_metrics_list(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    spec_level: str | None = Query(None, pattern="^L[1-4]$"),
):
    sessions, total = await list_session_metrics(
        limit=limit, offset=offset, spec_level=spec_level
    )
    return SessionMetricsListResponse(
        sessions=[SessionMetricsSummary(**s) for s in sessions],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/sessions/{session_id}")
async def session_metrics_detail(session_id: str):
    detail = await get_session_metrics_detail(session_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Session metrics not found")
    return detail


@router.post("/rebuild", response_model=RebuildStatsResponse)
async def rebuild_stats(force: bool = Query(False)):
    """Backfill metrics for sessions missing session_metrics rows."""
    result = await backfill_all_sessions(force=force)
    return RebuildStatsResponse(
        processed=result["processed"],
        skipped=result["skipped"],
        errors=result["errors"],
        message=f"Processed {result['processed']}, skipped {result['skipped']}, errors {result['errors']}",
    )
