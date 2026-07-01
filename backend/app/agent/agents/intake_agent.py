"""Intake agent — pre-flight clarification before the main pipeline runs."""

from __future__ import annotations

import json
import re
import uuid
from typing import Any

from app.agent.agents.base import BaseAgent
from app.agent.state import MultiAgentState
from app.services.language_validator import (
    output_language_instruction,
    should_validate_language,
    validate_intake_questions,
)

SYSTEM_PROMPT = """You are a senior product intake specialist. Before a multi-agent spec pipeline runs,
decide if the project idea has enough information to produce a useful specification.

Output ONLY valid JSON:
{
  "ready": true/false,
  "summary": "one sentence why ready or what is missing",
  "questions": [
    {
      "text": "clear question for the user",
      "priority": "critical|high|medium",
      "options": ["optional", "choices"],
      "required": true
    }
  ]
}

Rules:
- Set ready=true only if you can proceed without guessing critical product decisions.
- If ready=false, ask ALL missing questions at once (2-8 questions). Do not ask one-by-one.
- Use options array when a finite set of answers exists; use [] for free-text questions.
- Mark blocking unknowns as critical or high priority.
- questions array must be empty when ready=true.
- Write summary and every question "text" in the configured OUTPUT LANGUAGE.
- Translate human-readable option labels to the output language; keep technology/product names in Latin.
- Keep JSON keys and priority values (critical, high, medium) unchanged.
"""


class IntakeAgent(BaseAgent):
    agent_id = "intake"

    async def analyze(self, state: MultiAgentState) -> dict[str, Any]:
        """Return parsed intake result without mutating session state."""
        session_id = state["session_id"]
        rules = state.get("rules", {})
        hitl = rules.get("hitl", {}) or {}
        max_questions = int(hitl.get("max_intake_questions", 8))

        project = rules.get("project", {})
        constraints = rules.get("constraints", {})
        nfr = rules.get("nfr", {})
        agent_rules = rules.get("agent_rules", [])
        lang_block = output_language_instruction(rules)

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"{lang_block}\n\n"
                    f"Spec level: {state.get('spec_level', 'L2')}\n"
                    f"Project: {json.dumps(project, ensure_ascii=False)}\n"
                    f"Idea:\n{state['idea']}\n\n"
                    f"Constraints: {json.dumps(constraints, ensure_ascii=False)}\n"
                    f"NFR: {json.dumps(nfr, ensure_ascii=False)}\n"
                    f"Agent rules count: {len(agent_rules)}\n\n"
                    f"Ask at most {max_questions} questions if not ready. "
                    f"All question text MUST be in the output language above."
                ),
            },
        ]

        await self._log(session_id, "info", "Analyzing idea for missing information...")
        raw = await self._generate(state, messages)
        result = _parse_intake_result(raw, max_questions)

        if should_validate_language(rules) and result.get("questions"):
            expected = str((rules.get("output") or {}).get("language", "en"))
            violations = validate_intake_questions(result["questions"], expected)
            if violations:
                await self._log(
                    session_id,
                    "warn",
                    f"Intake questions language mismatch; regenerating ({violations[0]})",
                )
                repair_messages = [
                    *messages,
                    {"role": "assistant", "content": raw},
                    {
                        "role": "user",
                        "content": (
                            f"Your JSON failed language validation: {'; '.join(violations[:4])}\n"
                            f"{lang_block}\n"
                            "Regenerate ONLY valid JSON. "
                            "Every question text and the summary must be in the output language."
                        ),
                    },
                ]
                raw = await self._generate(state, repair_messages)
                result = _parse_intake_result(raw, max_questions)

        return result


def _parse_intake_result(raw: str, max_questions: int) -> dict[str, Any]:
    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if not match:
            return {"ready": True, "summary": "Could not parse intake; proceeding", "questions": []}
        try:
            data = json.loads(match.group())
        except json.JSONDecodeError:
            return {"ready": True, "summary": "Could not parse intake; proceeding", "questions": []}

    ready = bool(data.get("ready", True))
    questions = data.get("questions") or []
    if not isinstance(questions, list):
        questions = []

    normalized: list[dict[str, Any]] = []
    for q in questions[:max_questions]:
        if not isinstance(q, dict):
            continue
        text = str(q.get("text", "")).strip()
        if not text:
            continue
        normalized.append(
            {
                "id": str(q.get("id") or uuid.uuid4()),
                "text": text,
                "priority": q.get("priority", "high"),
                "options": q.get("options") or [],
                "required": q.get("required", True),
            }
        )

    if normalized:
        ready = False
    return {
        "ready": ready,
        "summary": str(data.get("summary", "")),
        "questions": normalized,
    }
