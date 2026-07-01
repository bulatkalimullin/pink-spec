"""Architect agent — C4 diagrams, ADRs, deployment, security boundaries."""

from __future__ import annotations

from typing import Any

from app.agent.agents.base import BaseAgent
from app.agent.state import MultiAgentState
from app.services.log_bus import log_bus

SYSTEM_PROMPT = """You are a Staff Software Architect. Based on the product specification, design the system architecture.

Output a detailed Markdown document with:
1. System Context (C4 Level 1) — users, external systems
2. Container Diagram (C4 Level 2) — services, databases, frontends
3. Key Architectural Decisions (ADR format: title, status, context, decision, consequences)
4. Technology Stack with justification for each choice
5. Data Model overview (entities, key relationships)
6. Deployment Architecture (local and/or cloud)
7. Security Boundaries (auth, data at rest, data in transit)
8. NFR Mapping (how architecture satisfies NFR requirements)
9. Known Trade-offs and Risks

Use Mermaid diagrams where appropriate. Mark assumptions with [ASSUMPTION].
"""


class ArchitectAgent(BaseAgent):
    agent_id = "architect"

    async def _execute(self, state: MultiAgentState) -> dict[str, Any]:
        session_id = state["session_id"]
        spec_level = state["spec_level"]
        rules = state["rules"]

        context = self._build_context(state)
        product_spec = state.get("artifacts", {}).get("product_spec", "")
        rules_snapshot = self._rules_snapshot(state)

        depth_instruction = {
            "L1": "Produce an architecture sketch: just system context and stack choice. Keep it brief.",
            "L2": "Produce C4 L1+L2, basic ADR for main decisions, deployment overview.",
            "L3": "Produce full architecture: C4 L1-L3, 3+ ADRs, security model, deployment.",
            "L4": "Produce exhaustive architecture: all C4 levels, all ADRs, detailed NFR analysis, ops runbook section.",
        }.get(spec_level, "Produce a standard architecture spec.")

        stack = rules.get("constraints", {}).get("stack", {})
        nfr = rules.get("nfr", {})
        output_lang = rules.get("output", {}).get("language", "en")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Product Specification:\n{product_spec[:3000]}\n\n"
                    f"Stack constraints: {stack}\nNFR: {nfr}\n\n"
                    f"{context}\n\n{rules_snapshot}\n\n"
                    f"Instructions: {depth_instruction}\nOutput language: {output_lang}"
                ),
            },
        ]

        await self._log(session_id, "info", "Designing architecture...")
        output = await self._llm.generate(messages)

        await log_bus.emit(
            session_id,
            "artifact_preview",
            {
                "artifact_type": "architecture_spec",
                "chunk": output[:500],
            },
        )

        assumptions = list(state.get("assumptions", []))
        for line in output.split("\n"):
            if "[ASSUMPTION]" in line:
                text = line.replace("[ASSUMPTION]", "").strip()
                assumptions.append(f"architect: {text}")
                await log_bus.emit(
                    session_id, "assumption_logged", {"text": text, "agent_id": self.agent_id}
                )

        new_outputs = {**state.get("agent_outputs", {}), "architect": output}
        new_artifacts = {**state.get("artifacts", {}), "architecture_spec": output}

        return {
            **state,
            "agent_outputs": new_outputs,
            "artifacts": new_artifacts,
            "assumptions": assumptions,
            "current_agent": "supervisor",
        }
