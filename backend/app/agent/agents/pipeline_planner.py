"""Pipeline Planner — builds dynamic agent pipeline from idea and rules."""

from __future__ import annotations

import json
import re
from typing import Any

from app.agent.agents.base import BaseAgent
from app.agent.pipeline_utils import (
    BUILTIN_STEP_META,
    TASK_COUNT_BY_LEVEL,
    legacy_sequence_to_steps,
    merge_deliverables_into_steps,
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
      "prompt_focus": "only for generic executor — what this spec must cover",
      "target_count": 60
    }
  ],
  "reasoning": "brief explanation of why these steps were chosen"
}

Rules:
- Do NOT include researcher or pipeline_planner — they already ran.
- Skip api_designer/ui_designer for backend-only, ML, or infra-only projects.
- Use executor "generic" for domain-specific specs (ml_pipeline_spec, security_spec, data_model, test_strategy, etc.).
- Include task_decomposer for L2+ unless idea is documentation-only.
- Include context_manager before task_decomposer for L3+.
- Include reviewer for L2+.
- target_count only on task_decomposer steps.
- artifact_key must be snake_case for generic steps.
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
        steps = self._apply_level_defaults(steps, spec_level, pipeline_cfg)
        steps = self._apply_idea_heuristics(steps, state["idea"])

        await log_bus.emit(
            session_id,
            "pipeline_planned",
            {
                "steps": steps,
                "reasoning": reasoning,
            },
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
        rules_snapshot = self._rules_snapshot(state)
        agent_rules = rules.get("agent_rules", [])
        rules_text = "\n".join(
            f"- [{r.get('priority', 'medium')}] {r.get('rule', '')}" for r in agent_rules[:15]
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Spec level: {spec_level}\n"
                    f"Idea: {state['idea']}\n"
                    f"Domain: {rules.get('project', {}).get('domain', 'general')}\n"
                    f"Stack backend: {rules.get('constraints', {}).get('stack', {}).get('backend', [])}\n"
                    f"Stack frontend: {rules.get('constraints', {}).get('stack', {}).get('frontend', [])}\n"
                    f"Include tasks hint: {rules.get('pipeline', {}).get('include_tasks')}\n"
                    f"User deliverables: {json.dumps(rules.get('pipeline', {}).get('deliverables', []))}\n"
                    f"Agent rules:\n{rules_text}\n\n{rules_snapshot}"
                ),
            },
        ]

        try:
            raw = await self._llm.generate(messages)
            data = _parse_json(raw)
            if not data:
                return [], ""
            reasoning = data.get("reasoning", "Pipeline planned from idea and rules")
            steps = data.get("steps", [])
            return _normalize_steps(steps, spec_level), reasoning
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
    ) -> list[dict[str, Any]]:
        ids = {s["id"] for s in steps}
        include_tasks = pipeline_cfg.get("include_tasks")
        if include_tasks is None:
            include_tasks = spec_level != "L1"

        if include_tasks and "task_decomposer" not in ids:
            steps.append(
                {
                    "id": "task_decomposer",
                    "name": "Task Decomposition",
                    "executor": "builtin:task_decomposer",
                    "artifact_key": None,
                    "required": spec_level != "L1",
                    "target_count": TASK_COUNT_BY_LEVEL.get(spec_level, 20),
                }
            )

        if spec_level in ("L2", "L3", "L4") and "reviewer" not in ids:
            steps.append(
                {
                    "id": "reviewer",
                    "name": "Reviewer",
                    "executor": "builtin:reviewer",
                    "artifact_key": None,
                    "required": True,
                }
            )

        if spec_level in ("L3", "L4") and "context_manager" not in ids:
            insert_at = next(
                (i for i, s in enumerate(steps) if s["id"] == "task_decomposer"),
                len(steps),
            )
            steps.insert(
                insert_at,
                {
                    "id": "context_manager",
                    "name": "Context Manager",
                    "executor": "builtin:context_manager",
                    "artifact_key": None,
                    "required": False,
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


def _normalize_steps(steps: list[dict], spec_level: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for s in steps:
        if not isinstance(s, dict) or not s.get("id"):
            continue
        step_id = s["id"]
        if step_id in ("researcher", "pipeline_planner", "export"):
            continue
        executor = s.get("executor", "generic")
        if executor.startswith("builtin:"):
            builtin_id = executor.split(":", 1)[1]
            if builtin_id in BUILTIN_STEP_META:
                meta = BUILTIN_STEP_META[builtin_id]
                out.append(
                    {
                        "id": builtin_id,
                        "name": s.get("name") or meta["name"],
                        "executor": meta["executor"],
                        "artifact_key": s.get("artifact_key", meta.get("artifact_key")),
                        "required": s.get("required", True),
                        "target_count": s.get("target_count")
                        if builtin_id == "task_decomposer"
                        else None,
                        "prompt_focus": s.get("prompt_focus"),
                    }
                )
                continue
        out.append(
            {
                "id": step_id,
                "name": s.get("name", step_id.replace("_", " ").title()),
                "executor": executor if executor == "generic" else "generic",
                "artifact_key": s.get("artifact_key", step_id),
                "required": s.get("required", True),
                "prompt_focus": s.get("prompt_focus", s.get("description", "")),
                "target_count": s.get("target_count"),
            }
        )
    return out
