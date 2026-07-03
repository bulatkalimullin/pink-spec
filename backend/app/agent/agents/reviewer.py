"""Reviewer agent — consistency, NFR, rules compliance."""

from __future__ import annotations

import json
import re
from typing import Any

from app.agent.agents.base import BaseAgent
from app.agent.agents.pipeline_planner import resolve_domain
from app.agent.domain_profiles import get_domain_deliverables, get_domain_review_checklist
from app.agent.state import MultiAgentState
from app.services.artifact_quality import load_existing_artifact_texts
from app.services.artifact_store import summarize_artifacts
from app.services.language_validator import (
    output_language_instruction,
    should_validate_language,
    validate_artifacts_language,
)
from app.agent.spec_maturity import build_maturity_prompt_block, resolve_spec_maturity

SYSTEM_PROMPT = """You are a senior engineering reviewer. Perform a quality review of all generated specifications.

Review for:
1. Internal consistency (no contradictions between specs)
2. NFR compliance (latency, availability, security requirements are addressed)
3. Rules compliance (all critical/high agent_rules are respected)
4. Completeness (no critical gaps)
5. Feasibility (realistic for stated timeline and budget)
6. Language compliance — prose must match the configured output language; technology names, API paths, statuses, and code stay untranslated

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
        artifacts_summary = await summarize_artifacts(session_id, max_per_key=1500)

        nfr = rules.get("nfr", {})
        agent_rules = rules.get("agent_rules", [])
        high_rules = [r for r in agent_rules if r.get("priority") in ("critical", "high")]
        assumptions = state.get("assumptions", [])
        lang_block = output_language_instruction(rules)
        domain = resolve_domain(state)
        maturity = resolve_spec_maturity(rules, state.get("spec_level", "L2"))
        domain_checklist = get_domain_review_checklist(domain, maturity)
        expected_deliverables = [d["artifact_key"] for d in get_domain_deliverables(domain, maturity)]
        pipeline_keys = {
            s.get("artifact_key")
            for s in (state.get("pipeline") or [])
            if s.get("artifact_key")
        }

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + build_maturity_prompt_block(maturity, domain)},
            {
                "role": "user",
                "content": (
                    f"{lang_block}\n"
                    f"Project domain: {domain}\n"
                    f"Spec maturity: {maturity}\n"
                    f"Domain review checklist:\n"
                    + "\n".join(f"- {c}" for c in domain_checklist)
                    + f"\n\nExpected deliverables for domain: {expected_deliverables}\n"
                    f"Pipeline artifact keys: {sorted(pipeline_keys)}\n"
                    f"NFR requirements: {json.dumps(nfr)}\n"
                    f"Critical/High rules: {json.dumps(high_rules)}\n"
                    f"Assumptions made: {json.dumps(assumptions[:20])}\n\n"
                    f"Artifacts to review:\n{artifacts_summary[:6000]}\n\n"
                    "Flag missing deliverables with location like lesson_plan#general and severity critical."
                ),
            },
        ]

        await self._log(
            session_id,
            "info",
            f"Running quality review (cycle #{state.get('review_cycles', 0) + 1})...",
        )
        raw = await self._generate(state, messages)
        report = _parse_report(raw)

        if not report:
            await self._log(
                session_id,
                "warn",
                "Reviewer returned invalid JSON; treating as failed review",
            )
            report = {
                "passed": False,
                "confidence": 0.0,
                "rules_compliant": False,
                "issues": [
                    {
                        "severity": "high",
                        "description": "Reviewer output was not valid JSON",
                        "location": "reviewer",
                    }
                ],
                "suggestions": ["Re-run review after artifacts are regenerated"],
                "summary": "Review parse error",
            }

        if should_validate_language(rules):
            expected_lang = str((rules.get("output") or {}).get("language", "en"))
            artifact_texts = load_existing_artifact_texts(session_id)
            lang_issues = validate_artifacts_language(artifact_texts, expected_lang)
            if lang_issues:
                report["issues"] = [*lang_issues, *report.get("issues", [])]
                report["passed"] = False
                if report.get("rules_compliant", True):
                    report["rules_compliant"] = False

        review_reports = [*state.get("review_reports", []), report]
        new_cycles = state.get("review_cycles", 0) + 1

        await log_bus.emit(
            session_id,
            "log_entry",
            {
                "level": "info" if report.get("passed") else "warn",
                "agent_id": "reviewer",
                "message": (
                    f"Review {'PASSED' if report.get('passed') else 'FAILED'} "
                    f"(confidence={report.get('confidence', 0):.2f}, "
                    f"issues={len(report.get('issues', []))})"
                ),
            },
        )

        run_id = self._run_id(state)
        new_outputs = {**state.get("agent_outputs", {}), run_id: json.dumps(report)}

        return {
            **state,
            "agent_outputs": new_outputs,
            "review_reports": review_reports,
            "review_cycles": new_cycles,
            "current_agent": "supervisor",
            "current_step": None,
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
