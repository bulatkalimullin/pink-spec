"""Pipeline Planner — builds dynamic agent pipeline from idea and rules."""

from __future__ import annotations

import json
import re
from typing import Any

from app.agent.agents.base import BaseAgent
from app.agent.stage_progress import emit_stage_changed
from app.agent.pipeline_utils import (
    BUILTIN_STEP_META,
    TASK_COUNT_BY_LEVEL,
    ensure_l4_deliverables,
    ensure_l4_task_batches,
    legacy_sequence_to_steps,
    merge_deliverables_into_steps,
    normalize_pipeline_steps,
)
from app.agent.state import MultiAgentState
from app.services.log_bus import log_bus

SYSTEM_PROMPT = """You are a specification pipeline planner. Given a project idea, spec level, and constraints,
design an ordered list of specification generation steps.

Output ONLY valid JSON:
{
  "steps": [
    {
      "id": "unique_step_id",
      "name": "Human-readable step name",
      "executor": "builtin:product_analyst" | "builtin:architect" | "builtin:api_designer" | "builtin:ui_designer" | "builtin:context_manager" | "builtin:task_decomposer" | "builtin:reviewer" | "generic",
      "artifact_key": "product_spec" | null,
      "required": true,
      "prompt_focus": "only for generic executor or task batches — what this step must cover",
      "target_count": 25
    }
  ],
  "reasoning": "brief explanation of why these steps were chosen"
}

Rules:
- Do NOT include researcher or pipeline_planner — they already ran.
- Skip api_designer/ui_designer for backend-only, ML, or infra-only projects.
- Use executor "generic" for domain-specific specs (security_spec, data_model, test_strategy, deployment_spec, observability_spec, risk_register, migration_plan, runbook, adr_log, etc.).
- Include task_decomposer for L2+ unless idea is documentation-only.
- For L3+: include context_manager before task decomposer steps.
- Include reviewer for L2+ (exactly once, at the end).
- target_count only on task_decomposer steps.
- artifact_key must be snake_case for generic steps.
- Each step id MUST be unique across the pipeline.
- For L4 (Exhaustive): plan 12–20 steps minimum. Split work into multiple generic deliverables.
  Use 4–6 separate task_decomposer steps with unique ids (e.g. tasks_foundation, tasks_backend)
  and prompt_focus limiting each batch to one phase. Never use a single monolithic step.
"""

BUILTIN_EXECUTORS = {
    "product_analyst",
    "architect",
    "api_designer",
    "ui_designer",
    "context_manager",
    "task_decomposer",
    "reviewer",
}


class PipelinePlannerAgent(BaseAgent):
    agent_id = "pipeline_planner"

    async def _execute(self, state: MultiAgentState) -> dict[str, Any]:
        session_id = state["session_id"]
        spec_level = state["spec_level"]
        rules = state["rules"]
        pipeline_cfg = rules.get("pipeline", {}) or {}
        deliverables = pipeline_cfg.get("deliverables", [])

        if pipeline_cfg.get("mode") == "fixed" or state.get("pipeline_planned"):
            return {**state, "current_agent": "supervisor"}

        await self._log(session_id, "info", "Planning dynamic specification pipeline...")

        steps, reasoning = await self._plan_with_llm(state)
        if not steps:
            steps = legacy_sequence_to_steps(spec_level)
            steps = [s for s in steps if s["id"] not in ("researcher", "pipeline_planner")]
            reasoning = "Fallback to default sequence for spec level"

        steps = merge_deliverables_into_steps(steps, deliverables)
        steps = self._apply_level_defaults(steps, spec_level, pipeline_cfg, rules)
        steps = self._apply_idea_heuristics(steps, state["idea"])

        await log_bus.emit(
            session_id,
            "pipeline_planned",
            {
                "steps": steps,
                "reasoning": reasoning,
            },
        )

        updated_state = {
            **state,
            "pipeline": steps,
            "pipeline_planned": True,
            "pipeline_reasoning": reasoning,
        }
        await emit_stage_changed(
            updated_state,
            stage_id="planning",
            label="Планируем пайплайн",
            detail=f"{len(steps)} шагов",
            agent_id="pipeline_planner",
            sub_progress=1.0,
        )

        from app.services.session import save_pipeline

        await save_pipeline(session_id, steps, reasoning)

        return {
            **state,
            "pipeline": steps,
            "pipeline_planned": True,
            "pipeline_reasoning": reasoning,
            "agent_outputs": {**state.get("agent_outputs", {}), "pipeline_planner": reasoning},
            "current_agent": "supervisor",
        }

    async def _plan_with_llm(self, state: MultiAgentState) -> tuple[list[dict[str, Any]], str]:
        spec_level = state["spec_level"]
        rules = state["rules"]
        pipeline_cfg = rules.get("pipeline", {}) or {}
        rules_snapshot = self._rules_snapshot(state)
        agent_rules = rules.get("agent_rules", [])
        rules_text = "\n".join(
            f"- [{r.get('priority', 'medium')}] {r.get('rule', '')}" for r in agent_rules[:15]
        )

        l4_hint = ""
        if spec_level == "L4":
            min_steps = pipeline_cfg.get("min_steps", 12)
            l4_hint = (
                f"\nL4 EXHAUSTIVE MODE: plan at least {min_steps} steps. "
                "Include 6+ generic deliverables and 4+ task_decomposer batches with unique ids."
            )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Spec level: {spec_level}{l4_hint}\n"
                    f"Idea: {state['idea']}\n"
                    f"Domain: {rules.get('project', {}).get('domain', 'general')}\n"
                    f"Stack backend: {rules.get('constraints', {}).get('stack', {}).get('backend', [])}\n"
                    f"Stack frontend: {rules.get('constraints', {}).get('stack', {}).get('frontend', [])}\n"
                    f"Include tasks hint: {pipeline_cfg.get('include_tasks')}\n"
                    f"User deliverables: {json.dumps(pipeline_cfg.get('deliverables', []))}\n"
                    f"Agent rules:\n{rules_text}\n\n{rules_snapshot}"
                ),
            },
        ]

        try:
            raw = await self._generate(state, messages)
            data = _parse_json(raw)
            if not data:
                return [], ""
            reasoning = data.get("reasoning", "Pipeline planned from idea and rules")
            steps = data.get("steps", [])
            return normalize_pipeline_steps(steps, spec_level), reasoning
        except Exception as e:
            await self._log(
                state["session_id"], "warn", f"LLM planner failed ({e}), using defaults"
            )
            return [], ""

    def _apply_level_defaults(
        self,
        steps: list[dict[str, Any]],
        spec_level: str,
        pipeline_cfg: dict,
        rules: dict,
    ) -> list[dict[str, Any]]:
        ids = {s["id"] for s in steps}
        include_tasks = pipeline_cfg.get("include_tasks")
        if include_tasks is None:
            include_tasks = spec_level != "L1"

        has_task_step = any(
            s.get("executor") == "builtin:task_decomposer"
            or s.get("executor_agent") == "task_decomposer"
            for s in steps
        )
        if include_tasks and not has_task_step:
            steps.append(
                {
                    "id": "task_decomposer",
                    "name": "Task Decomposition",
                    "executor": "builtin:task_decomposer",
                    "executor_agent": "task_decomposer",
                    "artifact_key": None,
                    "required": spec_level != "L1",
                    "target_count": TASK_COUNT_BY_LEVEL.get(spec_level, 20),
                }
            )

        if spec_level in ("L2", "L3", "L4") and "reviewer" not in ids and not any(
            s.get("executor_agent") == "reviewer" or s.get("id") == "reviewer" for s in steps
        ):
            steps.append(
                {
                    "id": "reviewer",
                    "name": "Reviewer",
                    "executor": "builtin:reviewer",
                    "executor_agent": "reviewer",
                    "artifact_key": None,
                    "required": True,
                }
            )

        if spec_level in ("L3", "L4") and "context_manager" not in ids and not any(
            s.get("executor_agent") == "context_manager" for s in steps
        ):
            insert_at = next(
                (
                    i
                    for i, s in enumerate(steps)
                    if s.get("executor_agent") == "task_decomposer"
                    or s.get("executor") == "builtin:task_decomposer"
                ),
                len(steps),
            )
            steps.insert(
                insert_at,
                {
                    "id": "context_manager",
                    "name": "Context Manager",
                    "executor": "builtin:context_manager",
                    "executor_agent": "context_manager",
                    "artifact_key": None,
                    "required": False,
                },
            )

        if spec_level == "L4":
            l4_cfg = rules.get("l4", {}) or {}
            min_deliverables = pipeline_cfg.get("min_deliverables", 8)
            min_steps = pipeline_cfg.get("min_steps", 12)
            tasks_per_batch = l4_cfg.get("tasks_per_batch", 25)

            steps = ensure_l4_deliverables(steps, min_deliverables)
            steps = ensure_l4_task_batches(steps, tasks_per_batch)

            while len(steps) < min_steps:
                extra_id = f"generic_extra_{len(steps)}"
                if any(s.get("id") == extra_id for s in steps):
                    break
                steps.insert(
                    max(len(steps) - 1, 0),
                    {
                        "id": extra_id,
                        "name": f"Additional Specification {len(steps)}",
                        "executor": "generic",
                        "artifact_key": extra_id,
                        "required": False,
                        "prompt_focus": "Additional domain-specific detail not covered elsewhere",
                    },
                )

        return steps

    def _apply_idea_heuristics(
        self, steps: list[dict[str, Any]], idea: str
    ) -> list[dict[str, Any]]:
        idea_lower = idea.lower()
        backend_only_signals = [
            "kafka",
            "pytorch",
            "ml pipeline",
            "fraud detection",
            "streaming",
            "etl",
            "data pipeline",
            "microservice",
            "backend only",
            "no ui",
        ]
        if any(sig in idea_lower for sig in backend_only_signals):
            steps = [
                s
                for s in steps
                if s.get("id") not in ("ui_designer", "api_designer")
                and s.get("executor_agent") not in ("ui_designer",)
                and s.get("artifact_key") not in ("ui_spec",)
            ]
            has_api = any(s.get("artifact_key") == "api_spec" for s in steps)
            if not has_api and any(w in idea_lower for w in ("api", "rest", "graphql", "fastapi")):
                meta = BUILTIN_STEP_META["api_designer"]
                steps.insert(
                    2,
                    {
                        "id": "api_designer",
                        "name": meta["name"],
                        "executor": meta["executor"],
                        "executor_agent": "api_designer",
                        "artifact_key": meta["artifact_key"],
                        "required": False,
                    },
                )
        return steps


def _parse_json(raw: str) -> dict | None:
    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None
