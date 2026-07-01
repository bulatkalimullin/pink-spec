"""Pydantic models for JSON rules config (schema_version: '1.0')."""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.schemas.pipeline import PipelineConfig


class SpecLevel(StrEnum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"


class Priority(StrEnum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"


class Deployment(StrEnum):
    local = "local"
    cloud = "cloud"
    on_prem = "on_prem"


class Budget(StrEnum):
    low = "low"
    medium = "medium"
    high = "high"


# --- Sub-models ---


class L4Config(BaseModel):
    safety_cap_sec: int = Field(7200, ge=300, le=14400)
    completion_confidence: float = Field(0.85, ge=0.5, le=1.0)
    tasks_coverage_pct: float = Field(95.0, ge=50.0, le=100.0)
    min_tasks: int = Field(100, ge=10, le=500)
    tasks_per_batch: int = Field(25, ge=5, le=50)
    max_task_batches: int = Field(8, ge=1, le=20)
    until_confident: bool = True


class ProjectConfig(BaseModel):
    name: str = "my-project"
    domain: str = "general"
    idea_summary: str | None = None


class StackConfig(BaseModel):
    backend: list[str] = Field(default_factory=list)
    frontend: list[str] = Field(default_factory=list)
    forbidden: list[str] = Field(default_factory=list)


class ConstraintsConfig(BaseModel):
    stack: StackConfig = Field(default_factory=StackConfig)
    deployment: Deployment = Deployment.local
    budget: Budget = Budget.low
    timeline_weeks: int = Field(8, ge=1, le=104)


class NFRConfig(BaseModel):
    latency_p95_ms: int | None = None
    availability: str | None = None
    security: list[str] = Field(default_factory=list)


class OutputLanguage(StrEnum):
    en = "en"
    ru = "ru"


class OutputConfig(BaseModel):
    """Language applies to generated specs; ui_language defaults to same value."""

    language: OutputLanguage = OutputLanguage.en
    ui_language: OutputLanguage | None = None
    validate_language: bool = True
    format: str = "markdown"
    include_diagrams: bool = True

    def resolved_ui_language(self) -> str:
        return (self.ui_language or self.language).value


class AgentRule(BaseModel):
    id: str
    priority: Priority = Priority.medium
    rule: str


class OllamaConfig(BaseModel):
    llm_model: str = "qwen2.5:7b"
    fallback_models: list[str] = Field(default_factory=list)
    embedding_model: str = "nomic-embed-text"
    embedding_fallback: str = "keyword"
    temperature: float = Field(0.2, ge=0.0, le=1.0)
    max_tokens: int = Field(4096, ge=256, le=32768)
    keep_alive: str = "5m"
    timeout_sec: int = Field(120, ge=10, le=600)


class HFConfig(BaseModel):
    """Deprecated — kept for backward compatibility with old rules JSON."""

    llm_model_id: str = "HuggingFaceH4/zephyr-7b-beta"
    fallback_model_ids: list[str] = Field(default_factory=list)
    embedding_model_id: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_fallback: str = "keyword"
    temperature: float = Field(0.2, ge=0.0, le=1.0)
    max_tokens: int = Field(4096, ge=256, le=32768)
    use_local: bool = False
    retry_on_rate_limit: int = Field(3, ge=0, le=10)
    retry_backoff_sec: list[float] = Field(default_factory=lambda: [2, 5, 15])


class SaturationConfig(BaseModel):
    max_iterations: int = Field(5, ge=1, le=20)
    novelty_threshold: float = Field(0.15, ge=0.0, le=1.0)
    min_chunks: int = Field(10, ge=1)
    query_expansion: bool = True


class RAGConfig(BaseModel):
    enabled: bool = True
    sources: list[str] = Field(default_factory=list)
    top_k: int = Field(8, ge=1, le=50)
    saturation: SaturationConfig = Field(default_factory=SaturationConfig)


class ContextConfig(BaseModel):
    summarization_enabled: bool = True
    max_raw_turns: int = Field(6, ge=2, le=20)
    compress_at_token_pct: int = Field(70, ge=50, le=90)


class ArtifactsConfig(BaseModel):
    mode: str = Field("auto", pattern="^(auto|generate|patch)$")
    max_patch_chars: int = Field(24000, ge=4000, le=100000)
    patch_fallback_generate: bool = False


class MonitoringConfig(BaseModel):
    enabled: bool = True
    interval_sec: int = Field(3, ge=1, le=60)
    warn_cpu_pct: float = Field(90.0, ge=50.0, le=100.0)
    warn_ram_pct: float = Field(85.0, ge=50.0, le=100.0)
    warn_gpu_mem_pct: float = Field(90.0, ge=50.0, le=100.0)
    show_per_core: bool = False


class HitlConfig(BaseModel):
    enabled: bool = True
    intake_before_start: bool = True
    max_intake_questions: int = Field(8, ge=0, le=20)


class ResilienceConfig(BaseModel):
    agent_timeout_sec: int = Field(600, ge=30, le=3600)
    stuck_detection_sec: int = Field(300, ge=30, le=1800)
    hitl_timeout_sec: int = Field(3600, ge=60)
    max_review_cycles: int = Field(10, ge=1, le=50)
    patch_unchanged_limit: int = Field(2, ge=1, le=10)
    review_plateau_window: int = Field(3, ge=2, le=10)
    circuit_breaker_failures: int = Field(3, ge=1, le=10)
    circuit_breaker_cooldown_sec: int = Field(60, ge=10, le=600)
    checkpoint_every_agent: bool = True
    auto_resume_on_reconnect: bool = True


# --- Root model ---


class Rules(BaseModel):
    schema_version: str = "1.0"
    spec_level: SpecLevel = SpecLevel.L2
    l4: L4Config = Field(default_factory=L4Config)
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    constraints: ConstraintsConfig = Field(default_factory=ConstraintsConfig)
    nfr: NFRConfig = Field(default_factory=NFRConfig)
    output: OutputConfig = Field(default_factory=OutputConfig)
    agent_rules: list[AgentRule] = Field(default_factory=list)
    ollama: OllamaConfig = Field(default_factory=OllamaConfig)
    hf: HFConfig | None = None
    rag: RAGConfig = Field(default_factory=RAGConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)
    artifacts: ArtifactsConfig = Field(default_factory=ArtifactsConfig)
    monitoring: MonitoringConfig = Field(default_factory=MonitoringConfig)
    resilience: ResilienceConfig = Field(default_factory=ResilienceConfig)
    hitl: HitlConfig = Field(default_factory=HitlConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)

    @model_validator(mode="after")
    def validate_l4_cap(self) -> Rules:
        if self.spec_level == SpecLevel.L4 and self.l4.safety_cap_sec > 14400:
            raise ValueError("L4 safety_cap_sec cannot exceed 4 hours (14400s)")
        return self

    @model_validator(mode="after")
    def apply_l4_defaults(self) -> Rules:
        if self.spec_level == SpecLevel.L4:
            if self.pipeline.min_steps is None:
                self.pipeline.min_steps = 12
            if self.pipeline.min_deliverables is None:
                self.pipeline.min_deliverables = 8
            if self.ollama.max_tokens < 8192:
                self.ollama.max_tokens = 8192
        return self

    def get_time_budget(self) -> int | None:
        budgets = {SpecLevel.L1: 300, SpecLevel.L2: 900, SpecLevel.L3: 1800, SpecLevel.L4: None}
        return budgets[self.spec_level]

    def critical_rules(self) -> list[AgentRule]:
        return [r for r in self.agent_rules if r.priority == Priority.critical]

    def high_and_above_rules(self) -> list[AgentRule]:
        return [r for r in self.agent_rules if r.priority in (Priority.critical, Priority.high)]


class StartSessionRequest(BaseModel):
    idea: str = Field(..., min_length=10, max_length=10000)
    rules: Rules = Field(default_factory=Rules)


class AnswerRequest(BaseModel):
    question_id: str
    answer: Any


class BatchAnswersRequest(BaseModel):
    answers: dict[str, Any] = Field(..., min_length=1)


class RecoverRequest(BaseModel):
    action: str = Field(
        ...,
        pattern=(
            "^(retry_agent|skip_agent|force_export|restart_from|replan_pipeline|"
            "retry_tasks|retry_reviewer|update_settings)$"
        ),
    )
    target_agent: str | None = None
    max_review_cycles: int | None = Field(None, ge=1, le=50)
    completion_confidence: float | None = Field(None, ge=0.5, le=1.0)
    until_confident: bool | None = None


class SessionControlRequest(BaseModel):
    """Live refinement settings and actions for a running session."""

    max_review_cycles: int | None = Field(None, ge=1, le=50)
    completion_confidence: float | None = Field(None, ge=0.5, le=1.0)
    until_confident: bool | None = None
    action: str | None = Field(
        None,
        pattern="^(replan_pipeline|retry_tasks|retry_reviewer|force_export|pause|resume|cancel)$",
    )
