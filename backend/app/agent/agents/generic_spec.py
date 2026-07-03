"""Generic specification agent — dynamic deliverable generation."""

from __future__ import annotations

from typing import Any

from app.agent.agents.base import BaseAgent
from app.agent.agents.pipeline_planner import resolve_domain
from app.agent.spec_maturity import build_maturity_prompt_block, resolve_spec_maturity
from app.agent.state import MultiAgentState
from app.services.artifact_store import summarize_artifacts
from app.services.log_bus import log_bus

SYSTEM_PROMPT = """You are a senior technical specification writer.
Produce a detailed Markdown specification document for the requested deliverable.

The document MUST start with metadata including exactly:
**Artifact Key:** <artifact_key from the request>

Structure the document with clear headings, actionable details, and explicit [ASSUMPTION] markers where you infer facts.
Reference related specifications when provided in context.
Do NOT copy boilerplate from other artifacts — each deliverable must be unique to its artifact key.
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
        prior = await summarize_artifacts(session_id, max_per_key=1200)

        output_lang = state["rules"].get("output", {}).get("language", "en")
        domain = resolve_domain(state)
        maturity = resolve_spec_maturity(state["rules"], state["spec_level"])
        maturity_block = build_maturity_prompt_block(maturity, domain)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + maturity_block},
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
        placeholder, mode, output, new_assumptions = await self._write_spec_artifact(
            state,
            artifact_key,
            generate_messages=messages,
            artifact_label=name,
        )

        await log_bus.emit(
            session_id,
            "artifact_preview",
            {
                "artifact_type": artifact_key,
                "chunk": output[:500],
                "mode": mode,
            },
        )

        run_id = step_id
        return {
            **state,
            "agent_outputs": {
                **state.get("agent_outputs", {}),
                run_id: output[:200] + "…" if len(output) > 200 else output,
            },
            "artifacts": {**state.get("artifacts", {}), artifact_key: placeholder},
            "assumptions": self._merge_assumptions(state, new_assumptions),
            "current_agent": "supervisor",
            "current_step": None,
        }
