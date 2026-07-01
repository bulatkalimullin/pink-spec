"""Product Analyst agent — personas, use cases, user stories, scope."""

from __future__ import annotations

from typing import Any

from app.agent.agents.base import BaseAgent
from app.agent.state import MultiAgentState
from app.services.log_bus import log_bus

SYSTEM_PROMPT = """You are a senior Product Analyst. Given a project idea and constraints, produce a comprehensive product specification.

Output a detailed Markdown document with these sections:
1. Executive Summary
2. Problem Statement
3. Target Users & Personas (2-4 personas with goals and frustrations)
4. Core Use Cases (numbered list)
5. User Stories (as a [user] I want [goal] so that [benefit])
6. Scope: MVP vs Future
7. Success Metrics (quantifiable KPIs)
8. Assumptions & Open Questions

Keep assumptions explicit with [ASSUMPTION] prefix.
"""


class ProductAnalystAgent(BaseAgent):
    agent_id = "product_analyst"

    async def _execute(self, state: MultiAgentState) -> dict[str, Any]:
        session_id = state["session_id"]
        spec_level = state["spec_level"]
        rules = state["rules"]

        context = self._build_context(state)
        rules_snapshot = self._rules_snapshot(state)

        depth_instruction = {
            "L1": "Produce a brief outline (1-2 pages). Focus on problem, users, and MVP scope only.",
            "L2": "Produce a standard spec (3-5 pages) with personas and core user stories.",
            "L3": "Produce a full spec with all sections, 4+ personas, 10+ user stories.",
            "L4": "Produce an exhaustive spec. Include edge cases, competitor analysis hints, and detailed metrics.",
        }.get(spec_level, "Produce a standard spec.")

        output_lang = rules.get("output", {}).get("language", "en")
        project_name = rules.get("project", {}).get("name", "the project")
        domain = rules.get("project", {}).get("domain", "general")
        constraints = rules.get("constraints", {})

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Project: {project_name}\nDomain: {domain}\n"
                    f"Idea: {state['idea']}\n\n"
                    f"Constraints: {constraints}\n\n"
                    f"{context}\n\n{rules_snapshot}\n\n"
                    f"Instructions: {depth_instruction}\nOutput language: {output_lang}"
                ),
            },
        ]

        await self._log(session_id, "info", "Generating product specification...")
        output = await self._llm.generate(messages)

        await log_bus.emit(
            session_id,
            "artifact_preview",
            {
                "artifact_type": "product_spec",
                "chunk": output[:500],
            },
        )

        # Extract assumptions
        assumptions = list(state.get("assumptions", []))
        for line in output.split("\n"):
            if "[ASSUMPTION]" in line:
                text = line.replace("[ASSUMPTION]", "").strip()
                assumptions.append(f"product_analyst: {text}")
                await log_bus.emit(
                    session_id, "assumption_logged", {"text": text, "agent_id": self.agent_id}
                )

        new_outputs = {**state.get("agent_outputs", {}), "product_analyst": output}
        new_artifacts = {**state.get("artifacts", {}), "product_spec": output}

        return {
            **state,
            "agent_outputs": new_outputs,
            "artifacts": new_artifacts,
            "assumptions": assumptions,
            "current_agent": "supervisor",
        }
