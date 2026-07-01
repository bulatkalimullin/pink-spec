"""UI Designer agent — screens, flows, component map."""

from __future__ import annotations

from typing import Any

from app.agent.agents.base import BaseAgent
from app.agent.state import MultiAgentState
from app.services.log_bus import log_bus

SYSTEM_PROMPT = """You are a senior UI/UX Designer and Frontend Architect. Design the complete UI specification.

Output a Markdown document covering:
1. Design principles and design system choice
2. Color palette and typography
3. Screen inventory (all screens with route, purpose, key actions)
4. User flows (step-by-step for critical paths, with ASCII art or Mermaid)
5. Component map (reusable components with props summary)
6. Responsive behavior notes
7. Accessibility requirements
8. State management approach

Mark assumptions with [ASSUMPTION].
"""


class UIDesignerAgent(BaseAgent):
    agent_id = "ui_designer"

    async def _execute(self, state: MultiAgentState) -> dict[str, Any]:
        session_id = state["session_id"]
        rules = state["rules"]

        product_spec = state.get("artifacts", {}).get("product_spec", "")
        architecture_spec = state.get("artifacts", {}).get("architecture_spec", "")
        context = self._build_context(state)
        rules_snapshot = self._rules_snapshot(state)
        frontend_stack = rules.get("constraints", {}).get("stack", {}).get("frontend", [])
        output_lang = rules.get("output", {}).get("language", "en")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Product Spec:\n{product_spec[:2000]}\n\n"
                    f"Architecture:\n{architecture_spec[:1000]}\n\n"
                    f"Frontend stack: {frontend_stack}\n\n"
                    f"{context}\n\n{rules_snapshot}\n\n"
                    f"Output language: {output_lang}"
                ),
            },
        ]

        await self._log(session_id, "info", "Designing UI screens and user flows...")
        output = await self._llm.generate(messages)

        await log_bus.emit(
            session_id,
            "artifact_preview",
            {
                "artifact_type": "ui_spec",
                "chunk": output[:500],
            },
        )

        assumptions = list(state.get("assumptions", []))
        for line in output.split("\n"):
            if "[ASSUMPTION]" in line:
                text = line.replace("[ASSUMPTION]", "").strip()
                assumptions.append(f"ui_designer: {text}")
                await log_bus.emit(
                    session_id, "assumption_logged", {"text": text, "agent_id": self.agent_id}
                )

        new_outputs = {**state.get("agent_outputs", {}), self._run_id(state): output}
        new_artifacts = {**state.get("artifacts", {}), "ui_spec": output}

        return {
            **state,
            "agent_outputs": new_outputs,
            "artifacts": new_artifacts,
            "assumptions": assumptions,
            "current_agent": "supervisor",
            "current_step": None,
        }
