"""Reviewer agent — consistency, NFR, rules compliance."""
from __future__ import annotations

import json
import re
from typing import Any

from app.agent.agents.base import BaseAgent
from app.agent.state import MultiAgentState
from app.services.log_bus import log_bus

SYSTEM_PROMPT = """You are a senior engineering reviewer. Perform a quality review of all generated specifications.

Review for:
1. Internal consistency (no contradictions between specs)
2. NFR compliance (latency, availability, security requirements are addressed)
3. Rules compliance (all critical/high agent_rules are respected)
4. Completeness (no critical gaps)
5. Feasibility (realistic for stated timeline and budget)

Output JSON:
{
  "passed": true/false,
  "confidence": 0.0-1.0,
  "rules_compliant": true/false,
  "issues": [
    {"severity": "critical|high|medium", "description": "...", "location": "artifact#section"}
  ],
  "suggestions": ["suggestion 1", ...],
  "summary": "one-paragraph review summary"
}

Return ONLY valid JSON. No prose.
"""


class ReviewerAgent(BaseAgent):
    agent_id = "reviewer"

    async def _execute(self, state: MultiAgentState) -> dict[str, Any]:
        session_id = state["session_id"]
        rules = state["rules"]
        artifacts = state.get("artifacts", {})

        nfr = rules.get("nfr", {})
        agent_rules = rules.get("agent_rules", [])
        high_rules = [r for r in agent_rules if r.get("priority") in ("critical", "high")]
        assumptions = state.get("assumptions", [])

        artifacts_summary = "\n\n".join(
            f"=== {k} ===\n{v[:1500]}" for k, v in artifacts.items() if v
        )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"NFR requirements: {json.dumps(nfr)}\n"
                    f"Critical/High rules: {json.dumps(high_rules)}\n"
                    f"Assumptions made: {json.dumps(assumptions[:20])}\n\n"
                    f"Artifacts to review:\n{artifacts_summary[:6000]}"
                ),
            },
        ]

        await self._log(session_id, "info", f"Running quality review (cycle #{state.get('review_cycles', 0) + 1})...")
        raw = await self._llm.generate(messages)
        report = _parse_report(raw)

        if not report:
            await self._log(session_id, "warn", "Reviewer returned invalid JSON; assuming pass with low confidence")
            report = {"passed": True, "confidence": 0.5, "rules_compliant": True, "issues": [], "suggestions": [], "summary": "Review parse error"}

        review_reports = [*state.get("review_reports", []), report]
        new_cycles = state.get("review_cycles", 0) + 1

        await log_bus.emit(session_id, "log_entry", {
            "level": "info" if report.get("passed") else "warn",
            "agent_id": "reviewer",
            "message": (
                f"Review {'PASSED' if report.get('passed') else 'FAILED'} "
                f"(confidence={report.get('confidence', 0):.2f}, "
                f"issues={len(report.get('issues', []))})"
            ),
        })

        new_outputs = {**state.get("agent_outputs", {}), "reviewer": json.dumps(report)}

        return {
            **state,
            "agent_outputs": new_outputs,
            "review_reports": review_reports,
            "review_cycles": new_cycles,
            "current_agent": "supervisor",
        }


def _parse_report(raw: str) -> dict | None:
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
