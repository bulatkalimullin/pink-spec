"""API Designer agent — REST/WS contracts, OpenAPI spec, data models."""

from __future__ import annotations

from typing import Any

from app.agent.agents.base import BaseAgent
from app.agent.state import MultiAgentState
from app.services.log_bus import log_bus

SYSTEM_PROMPT = """You are a senior API Designer. Design a comprehensive API specification based on the architecture.

Output two documents:

1. **API Specification (OpenAPI 3.1 YAML)** — for all REST endpoints and WebSocket contracts
2. **Data Model (Markdown)** — entities, fields, types, validation rules, relationships

For each endpoint include: path, method, description, request/response schemas, auth requirements, error codes.
Mark assumptions with [ASSUMPTION].
"""


class APIDesignerAgent(BaseAgent):
    agent_id = "api_designer"

    async def _execute(self, state: MultiAgentState) -> dict[str, Any]:
        session_id = state["session_id"]
        rules = state["rules"]

        architecture_spec = state.get("artifacts", {}).get("architecture_spec", "")
        product_spec = state.get("artifacts", {}).get("product_spec", "")
        context = self._build_context(state)
        rules_snapshot = self._rules_snapshot(state)
        output_lang = rules.get("output", {}).get("language", "en")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Architecture:\n{architecture_spec[:2000]}\n\n"
                    f"Product Spec:\n{product_spec[:1000]}\n\n"
                    f"{context}\n\n{rules_snapshot}\n\n"
                    f"Output language: {output_lang}"
                ),
            },
        ]

        await self._log(session_id, "info", "Designing API contracts and data models...")
        output = await self._llm.generate(messages)

        await log_bus.emit(
            session_id,
            "artifact_preview",
            {
                "artifact_type": "api_spec",
                "chunk": output[:500],
            },
        )

        assumptions = list(state.get("assumptions", []))
        for line in output.split("\n"):
            if "[ASSUMPTION]" in line:
                text = line.replace("[ASSUMPTION]", "").strip()
                assumptions.append(f"api_designer: {text}")
                await log_bus.emit(
                    session_id, "assumption_logged", {"text": text, "agent_id": self.agent_id}
                )

        run_id = self._run_id(state)
        new_outputs = {**state.get("agent_outputs", {}), run_id: output}
        new_artifacts = {
            **state.get("artifacts", {}),
            "api_spec": output,
            "data_model": output,
        }

        return {
            **state,
            "agent_outputs": new_outputs,
            "artifacts": new_artifacts,
            "assumptions": assumptions,
            "current_agent": "supervisor",
            "current_step": None,
        }
