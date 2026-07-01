"""Base class for all spec agents."""

from __future__ import annotations

import time
from typing import Any

import structlog

from app.agent.state import MultiAgentState
from app.services.log_bus import log_bus

logger = structlog.get_logger(__name__)

_AGENT_NAMES = {
    "product_analyst": "Product Analyst",
    "architect": "Architect",
    "api_designer": "API Designer",
    "ui_designer": "UI Designer",
    "task_decomposer": "Task Decomposer",
    "researcher": "Researcher",
    "reviewer": "Reviewer",
    "context_manager": "Context Manager",
    "pipeline_planner": "Pipeline Planner",
    "generic_spec": "Specification",
}


class BaseAgent:
    agent_id: str = "base"

    def __init__(self, llm) -> None:
        self._llm = llm

    async def run(self, state: MultiAgentState) -> dict[str, Any]:
        session_id = state["session_id"]
        step = state.get("current_step") or {}
        run_id = step.get("id") if step else self.agent_id
        call_count = state.get("agent_call_counts", {}).get(run_id, 1)
        agent_name = (
            getattr(self, "_display_name", None)
            or step.get("name")
            or _AGENT_NAMES.get(self.agent_id, self.agent_id)
        )

        await log_bus.emit(
            session_id,
            "agent_started",
            {
                "agent_id": run_id,
                "agent_name": agent_name,
                "pass_number": call_count,
            },
        )

        start = time.time()
        try:
            result = await self._execute(state)
            duration_ms = int((time.time() - start) * 1000)
            await log_bus.emit(
                session_id,
                "agent_completed",
                {
                    "agent_id": run_id,
                    "duration_ms": duration_ms,
                    "status": "success",
                },
            )
            return result
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            logger.exception("agent_error", agent=self.agent_id, error=str(e))
            await log_bus.emit(
                session_id,
                "agent_completed",
                {
                    "agent_id": run_id,
                    "duration_ms": duration_ms,
                    "status": "failed",
                },
            )
            return {
                **state,
                "agent_outputs": {**state.get("agent_outputs", {}), run_id: "failed"},
                "errors": [*state.get("errors", []), f"{run_id}: {e}"],
                "current_agent": "supervisor",
                "_last_agent_failed": True,
            }

    async def _execute(self, state: MultiAgentState) -> dict[str, Any]:
        raise NotImplementedError

    def _build_context(self, state: MultiAgentState) -> str:
        ctx = state.get("context", {})
        parts = []
        if ctx.get("phase_summary"):
            parts.append(f"[Phase Summary]\n{ctx['phase_summary']}")
        if ctx.get("turn_summaries"):
            parts.append("[Recent Agent Outputs]\n" + "\n".join(ctx["turn_summaries"][-3:]))
        if state.get("saturation_report", {}) and state["saturation_report"].get("context_brief"):
            parts.append("[RAG Context]\n" + state["saturation_report"]["context_brief"][:2000])
        return "\n\n".join(parts)

    def _rules_snapshot(self, state: MultiAgentState) -> str:
        rules = state.get("rules", {})
        agent_rules = rules.get("agent_rules", [])
        high_rules = [r for r in agent_rules if r.get("priority") in ("critical", "high")]
        if not high_rules:
            return ""
        lines = ["[Critical/High Rules]"]
        for r in high_rules:
            lines.append(f"- [{r['priority'].upper()}] {r['rule']}")
        return "\n".join(lines)

    async def _log(self, session_id: str, level: str, message: str) -> None:
        await log_bus.emit(
            session_id,
            "log_entry",
            {
                "level": level,
                "agent_id": self.agent_id,
                "message": message,
            },
        )

    async def _log_assumption(self, session_id: str, text: str) -> None:
        assumption = f"[ASSUMPTION] {self.agent_id}: {text}"
        await log_bus.emit(
            session_id,
            "assumption_logged",
            {
                "text": text,
                "agent_id": self.agent_id,
            },
        )
        return assumption

    def _run_id(self, state: MultiAgentState) -> str:
        step = state.get("current_step") or {}
        return step.get("id") or self.agent_id
