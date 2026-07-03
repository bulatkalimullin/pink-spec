"""LangGraph MultiAgentState and ContextState."""

from __future__ import annotations

from typing import Any, TypedDict


class ContextState(TypedDict):
    raw_turns: list[dict[str, Any]]
    turn_summaries: list[str]
    phase_summary: str
    session_summary: str
    token_budget_used: int
    saturation_report: dict[str, Any] | None


class MultiAgentState(TypedDict):
    # Identity
    session_id: str
    idea: str
    rules: dict[str, Any]
    spec_level: str  # L1|L2|L3|L4

    # Timing
    time_budget_sec: int | None
    safety_cap_sec: int
    started_at: float

    # Agent tracking
    current_agent: str
    agent_call_counts: dict[str, int]
    agent_durations: dict[str, int]
    review_cycles: int
    agent_outputs: dict[str, str]

    # Artifacts
    artifacts: dict[str, str]
    tasks: list[dict[str, Any]]

    # QA
    assumptions: list[str]
    decisions: list[dict[str, Any]]
    open_questions: list[dict[str, Any]]

    # Context
    context: ContextState
    saturation_report: dict[str, Any] | None

    # Supervisor
    supervisor_directives: dict[str, Any]
    review_reports: list[dict[str, Any]]

    # Health
    status: str  # running|paused|waiting_user|stuck|degraded|failed|completed|completed_partial
    errors: list[str]
    fallbacks_triggered: list[dict[str, Any]]

    # Recovery
    checkpoints: list[str]
    recovery_trace: list[dict[str, Any]]

    # Dynamic pipeline
    pipeline: list[dict[str, Any]]
    pipeline_planned: bool
    current_step: dict[str, Any] | None
    pipeline_reasoning: str
    pipeline_replan_cycles: int
    pipeline_version: int

    # Refinement patching
    refinement_issues: dict[str, list[dict[str, Any]]]
    patch_unchanged_counts: dict[str, int]
    refinement_pending: bool


def initial_state(
    session_id: str,
    idea: str,
    rules: dict[str, Any],
    time_budget_sec: int | None,
) -> MultiAgentState:
    import time

    rules = dict(rules)
    spec_level = rules.get("spec_level", "L2")
    safety_cap = rules.get("l4", {}).get("safety_cap_sec", 7200)
    pipeline_cfg = dict(rules.get("pipeline", {}) or {})
    mode = pipeline_cfg.get("mode", "auto")

    if spec_level == "L4":
        mode = "auto"
        pipeline_cfg["mode"] = "auto"
        from app.agent.spec_maturity import maturity_pipeline_defaults, resolve_spec_maturity

        maturity = resolve_spec_maturity(rules, spec_level)
        defaults = maturity_pipeline_defaults(maturity, spec_level)
        if pipeline_cfg.get("min_steps") is None:
            pipeline_cfg["min_steps"] = defaults["min_steps"]
        if pipeline_cfg.get("min_deliverables") is None:
            pipeline_cfg["min_deliverables"] = defaults["min_deliverables"]
        if pipeline_cfg.get("max_replan_cycles", 2) < defaults["max_replan_cycles"]:
            pipeline_cfg["max_replan_cycles"] = defaults["max_replan_cycles"]
        rules["pipeline"] = pipeline_cfg
        from app.agent.agents.pipeline_planner import apply_domain_l4_rules
        from app.agent.l4_guards import apply_l4_runtime_guards

        rules = apply_domain_l4_rules(rules)
        rules, _ = apply_l4_runtime_guards(rules)
    elif spec_level == "L3":
        from app.agent.spec_maturity import maturity_pipeline_defaults, resolve_spec_maturity

        maturity = resolve_spec_maturity(rules, spec_level)
        defaults = maturity_pipeline_defaults(maturity, spec_level)
        if pipeline_cfg.get("min_steps") is None:
            pipeline_cfg["min_steps"] = defaults["min_steps"]
        if pipeline_cfg.get("min_deliverables") is None:
            pipeline_cfg["min_deliverables"] = defaults["min_deliverables"]
        rules["pipeline"] = pipeline_cfg

    if mode == "fixed":
        from app.agent.pipeline_utils import legacy_sequence_to_steps

        pipeline = legacy_sequence_to_steps(spec_level)
        pipeline_planned = True
    else:
        from app.agent.pipeline_utils import initial_auto_pipeline

        pipeline = initial_auto_pipeline(spec_level)
        pipeline_planned = False

    return MultiAgentState(
        session_id=session_id,
        idea=idea,
        rules=rules,
        spec_level=spec_level,
        time_budget_sec=time_budget_sec,
        safety_cap_sec=safety_cap,
        started_at=time.time(),
        current_agent="supervisor",
        agent_call_counts={},
        agent_durations={},
        review_cycles=0,
        agent_outputs={},
        artifacts={},
        tasks=[],
        assumptions=[],
        decisions=[],
        open_questions=[],
        context=ContextState(
            raw_turns=[],
            turn_summaries=[],
            phase_summary="",
            session_summary="",
            token_budget_used=0,
            saturation_report=None,
        ),
        saturation_report=None,
        supervisor_directives={},
        review_reports=[],
        status="running",
        errors=[],
        fallbacks_triggered=[],
        checkpoints=[],
        recovery_trace=[],
        pipeline=pipeline,
        pipeline_planned=pipeline_planned,
        current_step=None,
        pipeline_reasoning="",
        pipeline_replan_cycles=0,
        pipeline_version=1,
        refinement_issues={},
        patch_unchanged_counts={},
        refinement_pending=False,
    )
