"""Generic specification agent — dynamic deliverable generation."""
from __future__ import annotations

from typing import Any

from app.agent.agents.base import BaseAgent
from app.agent.state import MultiAgentState
from app.services.log_bus import log_bus

SYSTEM_PROMPT = """You are a senior technical specification writer.
Produce a detailed Markdown specification document for the requested deliverable.

Structure the document with clear headings, actionable details, and explicit [ASSUMPTION] markers where you infer facts.
Reference related specifications when provided in context.
"""


class GenericSpecAgent(BaseAgent):
    agent_id = "generic_spec"

    async def run(self, state: MultiAgentState) -> dict[str, Any]:
        step = state.get("current_step") or {}
        self._display_name = step.get("name", "Specification")
        self._run_id = step.get("id", self.agent_id)
        return await super().run(state)

    async def _execute(self, state: MultiAgentState) -> dict[str, Any]:
        session_id = state["session_id"]
        step = state.get("current_step") or {}
        step_id = step.get("id", "generic_spec")
        artifact_key = step.get("artifact_key") or step_id
        name = step.get("name", artifact_key.replace("_", " ").title())
        prompt_focus = step.get("prompt_focus") or step.get("description") or ""

        context = self._build_context(state)
        rules_snapshot = self._rules_snapshot(state)
        artifacts = state.get("artifacts", {})
        prior = "\n\n".join(
            f"=== {k} ===\n{v[:1200]}" for k, v in artifacts.items() if v
        )

        output_lang = state["rules"].get("output", {}).get("language", "en")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Deliverable: {name}\n"
                    f"Artifact key: {artifact_key}\n"
                    f"Project idea: {state['idea']}\n"
                    f"Focus: {prompt_focus}\n\n"
                    f"Prior specifications:\n{prior}\n\n"
                    f"{context}\n\n{rules_snapshot}\n\n"
                    f"Output language: {output_lang}"
                ),
            },
        ]

        await self._log(session_id, "info", f"Generating {name}...")
        output = await self._llm.generate(messages)

        await log_bus.emit(session_id, "artifact_preview", {
            "artifact_type": artifact_key,
            "chunk": output[:500],
        })

        run_id = step_id
        return {
            **state,
            "agent_outputs": {**state.get("agent_outputs", {}), run_id: output[:200] + "…" if len(output) > 200 else output},
            "artifacts": {**state.get("artifacts", {}), artifact_key: output},
            "current_agent": "supervisor",
            "current_step": None,
        }
