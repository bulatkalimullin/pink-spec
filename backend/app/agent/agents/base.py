"""Base class for all spec agents."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog

from app.agent.stage_progress import (
    emit_stage_changed,
    generate_label_for_agent,
    record_agent_duration,
)
from app.agent.state import MultiAgentState
from app.services.artifact_quality import ArtifactQualityError, validate_artifact_for_save
from app.services.language_validator import (
    output_language_instruction,
    should_validate_language,
    validate_artifact_language,
)
from app.services.log_bus import log_bus
from app.services.session_runner import session_runner

logger = structlog.get_logger(__name__)

_AGENT_NAMES = {
    "product_analyst": "Product Analyst",
    "architect": "Architect",
    "api_designer": "API Designer",
    "ui_designer": "UI Designer",
    "task_decomposer": "Task Decomposer",
    "researcher": "Researcher",
    "reviewer": "Reviewer",
    "context_manager": "Context Manager",
    "pipeline_planner": "Pipeline Planner",
    "generic_spec": "Specification",
    "refinement_fixer": "Refinement Fixer",
}

PATCH_SYSTEM_PROMPT = """You are a specification editor. Improve the existing document with minimal targeted changes.

Do NOT rewrite the entire document. Return ONLY SEARCH/REPLACE blocks in this exact format:

<<<<<<< SEARCH
exact text copied from the document (must match verbatim)
=======
replacement text
>>>>>>> REPLACE

Rules:
- Each SEARCH block must match the file exactly (including whitespace).
- Make the smallest change that fixes the listed review issues.
- You may return multiple blocks.
- No markdown fences around the blocks. No commentary outside blocks.
"""

PATCH_REPAIR_PROMPT = """Your previous response had no valid or applicable SEARCH/REPLACE blocks.
Return ONLY corrected SEARCH/REPLACE blocks. Copy SEARCH text exactly from the document provided."""


class BaseAgent:
    agent_id: str = "base"

    def __init__(self, llm) -> None:
        self._llm = llm

    async def run(self, state: MultiAgentState) -> dict[str, Any]:
        session_id = state["session_id"]
        step = state.get("current_step") or {}
        run_id = step.get("id") if step else self.agent_id
        call_count = state.get("agent_call_counts", {}).get(run_id, 1)
        agent_name = (
            getattr(self, "_display_name", None)
            or step.get("name")
            or _AGENT_NAMES.get(self.agent_id, self.agent_id)
        )

        await log_bus.emit(
            session_id,
            "agent_started",
            {
                "agent_id": run_id,
                "agent_name": agent_name,
                "pass_number": call_count,
            },
        )

        await emit_stage_changed(
            state,
            stage_id="generate",
            label=generate_label_for_agent(state, run_id, agent_name),
            agent_id=run_id,
            sub_progress=0.1,
        )

        start = time.time()
        agent_task = asyncio.create_task(self._execute(state))
        session_runner.set_agent_task(session_id, agent_task)
        try:
            result = await agent_task
            duration_ms = int((time.time() - start) * 1000)
            duration_patch = record_agent_duration(
                {**state, **(result if isinstance(result, dict) else {})},
                run_id,
                duration_ms,
            )
            await log_bus.emit(
                session_id,
                "agent_completed",
                {
                    "agent_id": run_id,
                    "duration_ms": duration_ms,
                    "status": "success",
                },
            )
            merged = {**result, **duration_patch} if isinstance(result, dict) else duration_patch
            return merged
        except asyncio.CancelledError:
            duration_ms = int((time.time() - start) * 1000)
            await log_bus.emit(
                session_id,
                "agent_completed",
                {
                    "agent_id": run_id,
                    "duration_ms": duration_ms,
                    "status": "cancelled",
                },
            )
            return {
                **state,
                "current_agent": "supervisor",
                "errors": [*state.get("errors", []), f"{run_id}: cancelled"],
            }
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            logger.exception("agent_error", agent=self.agent_id, error=str(e))
            await log_bus.emit(
                session_id,
                "agent_completed",
                {
                    "agent_id": run_id,
                    "duration_ms": duration_ms,
                    "status": "failed",
                },
            )
            return {
                **state,
                "agent_outputs": {**state.get("agent_outputs", {}), run_id: "failed"},
                "errors": [*state.get("errors", []), f"{run_id}: {e}"],
                "current_agent": "supervisor",
                "_last_agent_failed": True,
            }
        finally:
            session_runner.set_agent_task(session_id, None)

    async def _execute(self, state: MultiAgentState) -> dict[str, Any]:
        raise NotImplementedError

    def _build_context(self, state: MultiAgentState) -> str:
        ctx = state.get("context", {})
        parts = []
        if ctx.get("phase_summary"):
            parts.append(f"[Phase Summary]\n{ctx['phase_summary']}")
        if ctx.get("turn_summaries"):
            parts.append("[Recent Agent Outputs]\n" + "\n".join(ctx["turn_summaries"][-3:]))
        if state.get("saturation_report", {}) and state["saturation_report"].get("context_brief"):
            parts.append("[RAG Context]\n" + state["saturation_report"]["context_brief"][:2000])
        return "\n\n".join(parts)

    def _llm_kwargs(self, state: MultiAgentState, **extra: Any) -> dict[str, Any]:
        """Per-session LLM options from rules.ollama (overrides global provider defaults)."""
        ollama = state.get("rules", {}).get("ollama", {}) or {}
        kwargs: dict[str, Any] = {}
        if "max_tokens" in ollama:
            kwargs["max_tokens"] = ollama["max_tokens"]
        if "temperature" in ollama:
            kwargs["temperature"] = ollama["temperature"]
        if "timeout_sec" in ollama:
            kwargs["timeout_sec"] = ollama["timeout_sec"]
        kwargs.update(extra)
        return kwargs

    async def _generate(self, state: MultiAgentState, messages: list[dict], **extra: Any) -> str:
        return await self._llm.generate(messages, **self._llm_kwargs(state, **extra))

    def _artifacts_cfg(self, state: MultiAgentState) -> dict[str, Any]:
        return state.get("rules", {}).get("artifacts", {}) or {}

    def _should_patch_artifact(self, state: MultiAgentState, artifact_key: str) -> bool:
        from app.services.artifact_store import artifact_exists

        cfg = self._artifacts_cfg(state)
        mode = cfg.get("mode", "auto")
        if mode == "generate":
            return False
        if mode == "patch":
            return artifact_exists(state["session_id"], artifact_key)
        return artifact_exists(state["session_id"], artifact_key)

    def _format_refinement_issues(self, state: MultiAgentState, artifact_key: str) -> str:
        issues = (state.get("refinement_issues") or {}).get(artifact_key, [])
        if not issues:
            return "Improve overall quality, completeness, and consistency."
        lines = []
        for issue in issues:
            sev = issue.get("severity", "medium")
            desc = issue.get("description", "")
            loc = issue.get("location", "")
            lines.append(f"- [{sev}] {desc} (at {loc})")
        return "\n".join(lines)

    async def _write_spec_artifact(
        self,
        state: MultiAgentState,
        artifact_key: str,
        *,
        generate_messages: list[dict],
        artifact_label: str,
    ) -> tuple[str, str, str, list[str]]:
        """
        Generate a new artifact or patch an existing one on disk.
        Returns (placeholder, mode, preview_text, extracted_assumptions).
        """
        from app.services.artifact_patcher import annotate_lines
        from app.services.artifact_store import (
            emit_artifact_generated,
            placeholder_for,
            read_artifact,
            save_artifact,
            save_artifact_patched,
        )

        session_id = state["session_id"]

        async def _generate_and_validate(messages: list[dict]) -> tuple[str, list[str]]:
            output = await self._generate(state, messages)
            rules = state.get("rules") or {}

            def _run_gates(text: str) -> tuple[str, list[str]]:
                content, assumptions = validate_artifact_for_save(
                    session_id,
                    artifact_key,
                    text,
                    check_duplicates=self.agent_id == "generic_spec",
                    require_key=self.agent_id == "generic_spec",
                )
                if should_validate_language(rules):
                    expected = str((rules.get("output") or {}).get("language", "en"))
                    lang_result = validate_artifact_language(content, artifact_key, expected)
                    if not lang_result.passed:
                        raise ArtifactQualityError("; ".join(lang_result.violations))
                return content, assumptions

            try:
                return _run_gates(output)
            except ArtifactQualityError as e:
                await self._log(
                    session_id,
                    "warn",
                    f"Artifact quality check failed for {artifact_key}: {e}. Retrying...",
                )
                lang_hint = output_language_instruction(rules)
                repair = messages + [
                    {
                        "role": "user",
                        "content": (
                            f"Your output failed validation: {e}\n"
                            f"{lang_hint}\n"
                            f"Regenerate the full document. "
                            f"First line after title MUST be: **Artifact Key:** {artifact_key}\n"
                            f"Do not duplicate content from other specification files."
                        ),
                    },
                ]
                output = await self._generate(state, repair)
                return _run_gates(output)

        if not self._should_patch_artifact(state, artifact_key):
            output, new_assumptions = await _generate_and_validate(generate_messages)
            placeholder = await save_artifact(session_id, artifact_key, output)
            await emit_artifact_generated(session_id, artifact_key, output)
            return placeholder, "generate", output, new_assumptions

        max_chars = int(self._artifacts_cfg(state).get("max_patch_chars", 24000))
        try:
            current = await asyncio.to_thread(read_artifact, session_id, artifact_key)
        except FileNotFoundError:
            output, new_assumptions = await _generate_and_validate(generate_messages)
            placeholder = await save_artifact(session_id, artifact_key, output)
            await emit_artifact_generated(session_id, artifact_key, output)
            return placeholder, "generate", output, new_assumptions

        body = current if len(current) <= max_chars else current[:max_chars]
        annotated = annotate_lines(body)
        issues_text = self._format_refinement_issues(state, artifact_key)

        patch_messages = [
            {"role": "system", "content": PATCH_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Artifact: {artifact_label} ({artifact_key})\n\n"
                    f"Review issues to fix:\n{issues_text}\n\n"
                    f"Current document:\n{annotated}"
                ),
            },
        ]

        await self._log(session_id, "info", f"Patching {artifact_label} ({artifact_key})...")
        raw = await self._generate(state, patch_messages)
        placeholder, result, mode = await save_artifact_patched(
            session_id, artifact_key, raw, original_content=current
        )

        if mode == "unchanged" and result.applied == 0:
            await self._log(session_id, "warn", f"Patch failed for {artifact_key}; retrying...")
            repair_messages = patch_messages + [
                {"role": "assistant", "content": raw[:4000]},
                {"role": "user", "content": PATCH_REPAIR_PROMPT},
            ]
            raw = await self._generate(state, repair_messages)
            placeholder, result, mode = await save_artifact_patched(
                session_id, artifact_key, raw, original_content=current
            )

        if mode == "unchanged":
            await self._log(
                session_id,
                "warn",
                f"Keeping existing {artifact_key} — patches did not apply",
            )
            from app.services.artifact_quality import extract_assumptions

            return placeholder_for(len(current)), "unchanged", current, extract_assumptions(current)

        patched_content = await asyncio.to_thread(read_artifact, session_id, artifact_key)
        return placeholder, mode, patched_content, extract_assumptions(patched_content)

    def _merge_assumptions(self, state: MultiAgentState, new_assumptions: list[str]) -> list[str]:
        merged = list(state.get("assumptions", []))
        for text in new_assumptions:
            entry = f"{self.agent_id}: {text}"
            if entry not in merged:
                merged.append(entry)
        return merged

    def _rules_snapshot(self, state: MultiAgentState) -> str:
        rules = state.get("rules", {})
        agent_rules = rules.get("agent_rules", [])
        high_rules = [r for r in agent_rules if r.get("priority") in ("critical", "high")]
        parts: list[str] = [output_language_instruction(rules)]
        if high_rules:
            parts.append("[Critical/High Rules]")
            for r in high_rules:
                parts.append(f"- [{r['priority'].upper()}] {r['rule']}")
        return "\n".join(parts)

    async def _log(self, session_id: str, level: str, message: str) -> None:
        await log_bus.emit(
            session_id,
            "log_entry",
            {
                "level": level,
                "agent_id": self.agent_id,
                "message": message,
            },
        )

    async def _log_assumption(self, session_id: str, text: str) -> None:
        assumption = f"[ASSUMPTION] {self.agent_id}: {text}"
        await log_bus.emit(
            session_id,
            "assumption_logged",
            {
                "text": text,
                "agent_id": self.agent_id,
            },
        )
        return assumption

    def _run_id(self, state: MultiAgentState) -> str:
        step = state.get("current_step") or {}
        return step.get("id") or self.agent_id
