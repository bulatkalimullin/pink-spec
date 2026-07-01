"""Pydantic models for statistics API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SessionMetricsSummary(BaseModel):
    session_id: str
    status: str
    spec_level: str
    completed_at: str
    duration_sec: float
    quality_score: float
    project_name: str | None = None
    output_slug: str | None = None
    artifacts_count: int = 0
    tasks_total: int = 0
    errors_count: int = 0
    efficiency_score: float = 0.0
    reliability_score: float = 0.0


class SessionMetricsListResponse(BaseModel):
    sessions: list[SessionMetricsSummary]
    total: int
    limit: int
    offset: int


class GlobalStatsResponse(BaseModel):
    updated_at: str
    totals: dict[str, Any] = Field(default_factory=dict)
    rates: dict[str, float] = Field(default_factory=dict)
    by_spec_level: dict[str, Any] = Field(default_factory=dict)
    agent_leaderboard: list[dict[str, Any]] = Field(default_factory=list)
    trends: dict[str, Any] = Field(default_factory=dict)
    reliability: dict[str, Any] = Field(default_factory=dict)
    infrastructure: dict[str, Any] = Field(default_factory=dict)
    recent_sessions: list[SessionMetricsSummary] = Field(default_factory=list)


class RebuildStatsResponse(BaseModel):
    processed: int
    skipped: int
    errors: int
    message: str
