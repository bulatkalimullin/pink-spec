"""Pipeline step models for dynamic spec generation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class PipelineStep(BaseModel):
    id: str
    name: str
    executor: str = "generic"
    artifact_key: str | None = None
    required: bool = True
    prompt_focus: str | None = None
    target_count: int | None = None
    description: str = ""
    executor_agent: str | None = None


class DeliverableSpec(BaseModel):
    id: str
    name: str
    artifact_key: str
    description: str = ""
    required: bool = True
    prompt_hint: str | None = None
    skip: bool = False


class PipelineConfig(BaseModel):
    mode: Literal["auto", "fixed"] = "auto"
    deliverables: list[DeliverableSpec] = Field(default_factory=list)
    include_tasks: bool | None = None
    min_steps: int | None = Field(None, ge=1, le=50)
    min_deliverables: int | None = Field(None, ge=0, le=30)
    max_replan_cycles: int = Field(2, ge=0, le=10)


def step_to_dict(step: PipelineStep | dict[str, Any]) -> dict[str, Any]:
    if isinstance(step, PipelineStep):
        return step.model_dump()
    return step


def steps_to_dicts(steps: list[PipelineStep | dict[str, Any]]) -> list[dict[str, Any]]:
    return [step_to_dict(s) for s in steps]
