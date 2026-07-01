"""Task Decomposer agent — breaks roadmap into micro-tasks (15-60 min each)."""
from __future__ import annotations

import json
import re
from typing import Any

from app.agent.agents.base import BaseAgent
from app.agent.pipeline_utils import TASK_COUNT_BY_LEVEL
from app.agent.state import MultiAgentState
from app.services.export import write_task_roadmap
from app.services.log_bus import log_bus

SYSTEM_PROMPT = """You are a senior engineering lead. Decompose the project specifications into atomic implementation tasks.

Each task must take 15–60 minutes to complete. Output a JSON array of task objects.

Each task object must have:
- id: "NNN" (zero-padded, sequential)
- phase: "XX-phase-name"
- title: "short imperative verb phrase"
- priority: "high" | "medium" | "low"
- estimated_minutes: 15-60
- depends_on: ["NNN", ...]
- spec_refs: ["docs/product_spec.md#section", "docs/architecture_spec.md#section", ...]
- goal: "one sentence — what works when done"
- context: "2-3 sentences explaining relationship to overall project"
- steps: ["step 1", "step 2", ...]
- acceptance_criteria: ["criterion 1", ...]
- notes: ["pitfall or note", ...]
- verification: "how to verify completion"

Group tasks into logical phases: 01-foundation, 02-backend, 03-frontend, etc.
Return ONLY valid JSON array. No prose.
"""

ROADMAP_PROMPT = """Summarize the implementation roadmap in Markdown based on the task list.
Include phases, key milestones, and links to spec documents under docs/.
Keep under 600 words.
"""


class TaskDecomposerAgent(BaseAgent):
    agent_id = "task_decomposer"

    async def _execute(self, state: MultiAgentState) -> dict[str, Any]:
        session_id = state["session_id"]
        spec_level = state["spec_level"]
        rules = state["rules"]
        step = state.get("current_step") or {}

        target_count = step.get("target_count") or TASK_COUNT_BY_LEVEL.get(spec_level, 20)
        run_id = step.get("id", self.agent_id)

        if target_count == 0:
            await self._log(session_id, "info", "Task decomposition skipped for this level")
            return {
                **state,
                "agent_outputs": {**state.get("agent_outputs", {}), run_id: "skipped"},
                "current_agent": "supervisor",
                "current_step": None,
            }

        artifacts = state.get("artifacts", {})
        product_spec = artifacts.get("product_spec", "")
        architecture_spec = artifacts.get("architecture_spec", "")
        api_spec = artifacts.get("api_spec", "")
        ui_spec = artifacts.get("ui_spec", "")
        extra_specs = "\n".join(
            f"=== {k} ===\n{v[:800]}"
            for k, v in artifacts.items()
            if k not in ("product_spec", "architecture_spec", "api_spec", "ui_spec") and v
        )
        output_lang = rules.get("output", {}).get("language", "en")

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Generate approximately {target_count} tasks for:\n\n"
                    f"Product:\n{product_spec[:1500]}\n\n"
                    f"Architecture:\n{architecture_spec[:1500]}\n\n"
                    f"API:\n{api_spec[:800]}\n\n"
                    f"UI:\n{ui_spec[:800]}\n\n"
                    f"Additional specs:\n{extra_specs[:2000]}\n\n"
                    f"Use spec_refs paths like docs/product_spec.md#section-name\n"
                    f"Output language for human-readable fields: {output_lang}"
                ),
            },
        ]

        await self._log(session_id, "info", f"Decomposing into ~{target_count} micro-tasks...")
        raw = await self._llm.generate(messages)
        tasks = _parse_tasks(raw)

        if not tasks:
            await self._log(session_id, "warn", "Invalid JSON — retrying with repair prompt")
            repair_messages = messages + [
                {"role": "assistant", "content": raw[:4000]},
                {
                    "role": "user",
                    "content": "Your output was not valid JSON. Return ONLY a valid JSON array of task objects. No markdown fences.",
                },
            ]
            raw = await self._llm.generate(repair_messages)
            tasks = _parse_tasks(raw)

        if not tasks:
            await self._log(session_id, "warn", "Task decomposer returned empty/invalid JSON")
            tasks = []
        else:
            tasks = _normalize_spec_refs(tasks)

        phases: dict[str, int] = {}
        for t in tasks:
            phase = t.get("phase", "00-unknown")
            phases[phase] = phases.get(phase, 0) + 1

        for phase, count in phases.items():
            await log_bus.emit(session_id, "task_batch_generated", {
                "phase": phase, "count": count
            })

        await self._log(session_id, "info", f"Generated {len(tasks)} tasks in {len(phases)} phases")

        roadmap_md = ""
        if tasks:
            try:
                roadmap_md = await self._llm.generate([
                    {"role": "system", "content": ROADMAP_PROMPT},
                    {"role": "user", "content": json.dumps(tasks[:30], indent=2)[:6000]},
                ])
                write_task_roadmap(session_id, roadmap_md)
            except Exception:
                roadmap_md = _fallback_roadmap(tasks)
                write_task_roadmap(session_id, roadmap_md)

        new_artifacts = dict(artifacts)
        if roadmap_md:
            new_artifacts["TASK_ROADMAP"] = roadmap_md

        return {
            **state,
            "agent_outputs": {**state.get("agent_outputs", {}), run_id: f"{len(tasks)} tasks"},
            "artifacts": new_artifacts,
            "tasks": tasks,
            "current_agent": "supervisor",
            "current_step": None,
        }


def _normalize_spec_refs(tasks: list[dict]) -> list[dict]:
    for t in tasks:
        refs = t.get("spec_refs", [])
        normalized = []
        for r in refs:
            if not r.startswith("docs/") and r.endswith(".md"):
                normalized.append(f"docs/{r}")
            elif not r.startswith("docs/") and "#" in r:
                parts = r.split("#", 1)
                normalized.append(f"docs/{parts[0]}.md#{parts[1]}" if not parts[0].startswith("docs/") else r)
            else:
                normalized.append(r if r.startswith("docs/") else f"docs/{r}")
        t["spec_refs"] = normalized
    return tasks


def _fallback_roadmap(tasks: list[dict]) -> str:
    lines = ["# Implementation Roadmap\n"]
    phases: dict[str, list[dict]] = {}
    for t in tasks:
        phases.setdefault(t.get("phase", "00-unknown"), []).append(t)
    for phase, items in sorted(phases.items()):
        lines.append(f"\n## {phase}\n")
        for t in items[:10]:
            lines.append(f"- **{t.get('id')}** {t.get('title', '')}\n")
    return "".join(lines)


def _parse_tasks(raw: str) -> list[dict]:
    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    try:
        data = json.loads(raw)
        if isinstance(data, list):
            return data
        return []
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", raw, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        return []
