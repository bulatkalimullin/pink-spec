"""Batch refinement agent — patch all reviewer issues in one pass, then re-review."""

from __future__ import annotations

import asyncio
from typing import Any

from app.agent.agents.base import BaseAgent, PATCH_REPAIR_PROMPT, PATCH_SYSTEM_PROMPT
from app.agent.spec_maturity import build_maturity_prompt_block, resolve_spec_maturity
from app.agent.state import MultiAgentState
from app.agent.supervisor import is_artifact_patch_exhausted, update_patch_unchanged_counts
from app.services.artifact_store import artifact_exists, placeholder_for, read_artifact
from app.services.log_bus import log_bus


class RefinementFixerAgent(BaseAgent):
    agent_id = "refinement_fixer"

    async def _execute(self, state: MultiAgentState) -> dict[str, Any]:
        session_id = state["session_id"]
        refinement_issues = state.get("refinement_issues") or {}
        if not refinement_issues:
            return self._finish(state, "no issues to patch", {}, {})

        artifact_keys = [k for k in refinement_issues if artifact_exists(session_id, k)]
        skipped = [k for k in refinement_issues if k not in artifact_keys]
        exhausted = [k for k in artifact_keys if is_artifact_patch_exhausted(state, k)]
        to_patch = [k for k in artifact_keys if k not in exhausted]

        total_issues = sum(len(refinement_issues[k]) for k in to_patch)
        await self._log(
            session_id,
            "info",
            (
                f"Batch patch: {len(to_patch)} artifact(s), {total_issues} issue(s)"
                + (f" ({len(exhausted)} skipped — patch exhausted)" if exhausted else "")
                + (f" ({len(skipped)} missing on disk)" if skipped else "")
            ),
        )
        await log_bus.emit(
            session_id,
            "refinement_batch_started",
            {
                "artifacts": to_patch,
                "issue_count": total_issues,
                "skipped_exhausted": exhausted,
                "skipped_missing": skipped,
            },
        )

        patch_counts = dict(state.get("patch_unchanged_counts") or {})
        new_artifacts = dict(state.get("artifacts", {}))
        summary_parts: list[str] = []

        for artifact_key in to_patch:
            label = artifact_key.replace("_", " ").title()
            placeholder, mode, _content, counts = await self._patch_artifact_batch(
                state, artifact_key, label, patch_counts
            )
            patch_counts = counts
            if mode in ("patch", "generate"):
                new_artifacts[artifact_key] = placeholder
            summary_parts.append(f"{artifact_key}:{mode}")

        summary = f"patched {len(summary_parts)} — " + ", ".join(summary_parts)
        return self._finish(state, summary, new_artifacts, patch_counts)

    async def _patch_artifact_batch(
        self,
        state: MultiAgentState,
        artifact_key: str,
        artifact_label: str,
        patch_counts: dict[str, int],
    ) -> tuple[str, str, str, dict[str, int]]:
        from app.services.artifact_patcher import annotate_lines
        from app.services.artifact_store import save_artifact_patched

        session_id = state["session_id"]
        max_chars = int(self._artifacts_cfg(state).get("max_patch_chars", 24000))

        try:
            current = await asyncio.to_thread(read_artifact, session_id, artifact_key)
        except FileNotFoundError:
            counts = update_patch_unchanged_counts(
                {**state, "patch_unchanged_counts": patch_counts}, artifact_key, "unchanged"
            )
            return placeholder_for(0), "unchanged", "", counts

        body = current if len(current) <= max_chars else current[:max_chars]
        annotated = annotate_lines(body)
        issues_text = self._format_refinement_issues(state, artifact_key)
        issue_count = len((state.get("refinement_issues") or {}).get(artifact_key, []))
        rules = state.get("_rules_snapshot") or {}
        maturity = resolve_spec_maturity(rules, str(rules.get("spec_level", "L2")))
        domain = str((rules.get("project") or {}).get("domain", "general"))
        maturity_block = build_maturity_prompt_block(maturity, domain)

        patch_messages = [
            {
                "role": "system",
                "content": (
                    f"{PATCH_SYSTEM_PROMPT}\n\n{maturity_block}\n\n"
                    "Fix ALL listed issues in this response. "
                    "Do not simplify production scope to MVP unless marked [DEFERRED]. "
                    "Use as many SEARCH/REPLACE blocks as needed."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Artifact: {artifact_label} ({artifact_key})\n"
                    f"Issues to fix ({issue_count}):\n{issues_text}\n\n"
                    f"Current document:\n{annotated}"
                ),
            },
        ]

        await self._log(session_id, "info", f"Patching {artifact_label} ({issue_count} issues)...")
        raw = await self._generate(state, patch_messages)
        placeholder, result, mode = await save_artifact_patched(
            session_id, artifact_key, raw, original_content=current
        )

        if mode == "unchanged" and result.applied == 0:
            repair_messages = patch_messages + [
                {"role": "assistant", "content": raw[:4000]},
                {"role": "user", "content": PATCH_REPAIR_PROMPT},
            ]
            raw = await self._generate(state, repair_messages)
            placeholder, result, mode = await save_artifact_patched(
                session_id, artifact_key, raw, original_content=current
            )

        counts = update_patch_unchanged_counts(
            {**state, "patch_unchanged_counts": patch_counts}, artifact_key, mode
        )

        if mode == "unchanged":
            await self._log(
                session_id,
                "warn",
                f"No applicable patches for {artifact_key} — keeping existing content",
            )
            return placeholder_for(len(current)), "unchanged", current, counts

        patched_content = await asyncio.to_thread(read_artifact, session_id, artifact_key)
        return placeholder, mode, patched_content, counts

    def _finish(
        self,
        state: MultiAgentState,
        summary: str,
        new_artifacts: dict[str, str],
        patch_counts: dict[str, int],
    ) -> dict[str, Any]:
        pipeline = state.get("pipeline") or []
        outputs = dict(state.get("agent_outputs", {}))
        outputs[self.agent_id] = summary
        for step in pipeline:
            if step.get("executor", "").endswith(":reviewer") or step.get(
                "executor_agent"
            ) == "reviewer":
                outputs.pop(step.get("id", "reviewer"), None)

        merged_artifacts = {**state.get("artifacts", {}), **new_artifacts}
        return {
            **state,
            "agent_outputs": outputs,
            "artifacts": merged_artifacts,
            "patch_unchanged_counts": patch_counts,
            "refinement_pending": False,
            "current_agent": "supervisor",
            "current_step": None,
        }
