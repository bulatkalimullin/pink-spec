"""Context Manager agent — summarization and context compression."""

from __future__ import annotations

from typing import Any

from app.agent.agents.base import BaseAgent
from app.agent.state import MultiAgentState

SYSTEM_PROMPT = """You are a context manager. Produce a concise structured summary.

Output exactly these sections in Markdown:
## Decisions
List concrete decisions made so far.

## Assumptions
List all [ASSUMPTION] items from agent outputs.

## Open Items
List any unresolved questions or gaps.

## Artifacts Touched
List artifacts that exist with a one-line status.

Keep total output under 800 tokens.
"""


class ContextManagerAgent(BaseAgent):
    agent_id = "context_manager"

    async def _execute(self, state: MultiAgentState) -> dict[str, Any]:
        session_id = state["session_id"]
        rules = state["rules"]

        if not rules.get("context", {}).get("summarization_enabled", True):
            return {**state, "current_agent": "supervisor"}

        agent_outputs = state.get("agent_outputs", {})
        recent_outputs = "\n\n".join(f"=== {k} ===\n{v[:600]}" for k, v in agent_outputs.items())

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"Summarize the following agent outputs:\n\n{recent_outputs}",
            },
        ]

        await self._log(session_id, "info", "Summarizing context...")
        summary = await self._generate(state, messages)

        new_context = dict(state.get("context", {}))
        turn_summaries = list(new_context.get("turn_summaries", []))
        turn_summaries.append(summary)
        new_context["turn_summaries"] = turn_summaries[-10:]  # keep last 10
        new_context["phase_summary"] = summary

        from app.services.log_bus import log_bus

        await log_bus.emit(
            session_id,
            "summary_updated",
            {
                "level": "phase",
                "preview": summary[:200],
            },
        )

        run_id = self._run_id(state)
        new_outputs = {**state.get("agent_outputs", {}), run_id: "done"}

        return {
            **state,
            "agent_outputs": new_outputs,
            "context": new_context,
            "current_agent": "supervisor",
            "current_step": None,
        }
