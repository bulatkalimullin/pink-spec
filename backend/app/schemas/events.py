"""WS envelope types and all event payload models."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(UTC).isoformat()


class WSEnvelope(BaseModel):
    type: str
    ts: str = Field(default_factory=_now)
    seq: int = 0
    session_id: str
    payload: dict[str, Any] = Field(default_factory=dict)


# --- Payload models ---


class LogEntryPayload(BaseModel):
    level: Literal["debug", "info", "warn", "error"]
    agent_id: str
    message: str
    tags: list[str] = Field(default_factory=list)


class SupervisorRoutingPayload(BaseModel):
    next_agent: str
    reason: str
    remaining_sec: int | None = None


class AgentStartedPayload(BaseModel):
    agent_id: str
    agent_name: str
    pass_number: int = 1


class AgentCompletedPayload(BaseModel):
    agent_id: str
    duration_ms: int
    status: Literal["success", "degraded", "failed"]


class FallbackTriggeredPayload(BaseModel):
    layer: str
    step: str
    message: str
    from_: str | None = Field(None, alias="from")
    to: str | None = None

    model_config = {"populate_by_name": True}


class AssumptionLoggedPayload(BaseModel):
    text: str
    agent_id: str
    assumption_id: str = Field(default_factory=lambda: str(uuid4())[:8])


class QuestionAskedPayload(BaseModel):
    question_id: str
    text: str
    options: list[str] = Field(default_factory=list)
    priority: str = "medium"


class CompletionCheckPayload(BaseModel):
    criteria: dict[str, bool]
    all_met: bool


class BudgetWarningPayload(BaseModel):
    remaining_sec: int
    mode: Literal["time_budget", "safety_cap"]


class ArtifactPreviewPayload(BaseModel):
    artifact_type: str
    chunk: str


class TaskBatchPayload(BaseModel):
    phase: str
    count: int


class CheckpointPayload(BaseModel):
    checkpoint_id: str
    agent_id: str


class SessionStuckPayload(BaseModel):
    reason: str
    since_sec: int
    suggested_actions: list[str]


class CircuitBreakerPayload(BaseModel):
    agent_id: str
    retry_after_sec: int | None = None


class SystemMetricsPayload(BaseModel):
    cpu_percent: float
    ram_percent: float
    ram_used_mb: float
    ram_total_mb: float
    swap_percent: float
    disk_percent: float
    process_rss_mb: float
    gpu: dict[str, Any] | None = None
    per_cpu: list[float] | None = None


class SystemWarningPayload(BaseModel):
    metric: str
    value: float
    threshold: float
    hint: str


class DonePayload(BaseModel):
    duration_sec: float
    artifacts_count: int
    tasks_count: int
    assumptions_count: int
    fallbacks_count: int
    is_partial: bool = False


class ErrorPayload(BaseModel):
    code: str
    message: str
    recoverable: bool = True
