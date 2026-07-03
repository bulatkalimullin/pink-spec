"""Pipeline Planner — builds dynamic domain-agnostic pipeline from idea and rules."""

from __future__ import annotations

import json
import re
from typing import Any

from app.agent.agents.base import BaseAgent
from app.agent.domain_profiles import (
    detect_domain,
    get_domain_deliverables,
    get_domain_l4_tasks_config,
    get_domain_work_packages,
    get_profile,
    normalize_domain,
    work_packages_to_pipeline_steps,
)
from app.agent.stage_progress import emit_stage_changed
from app.agent.pipeline_utils import (
    TASK_COUNT_BY_LEVEL,
    ensure_domain_deliverables,
    ensure_domain_work_packages,
    expand_prod_deliverables,
    insert_pipeline_steps_before_reviewer,
    legacy_sequence_to_steps,
    merge_deliverables_into_steps,
    named_prod_fillers,
    normalize_pipeline_steps,
    step_builtin_agent_id,
)
from app.agent.spec_maturity import (
    build_maturity_prompt_block,
    maturity_pipeline_defaults,
    resolve_spec_maturity,
)
from app.agent.state import MultiAgentState
from app.services.artifact_store import summarize_artifacts
from app.services.log_bus import log_bus

SYSTEM_PROMPT = """You are a specification pipeline planner. Given a project idea, spec level, domain, and constraints,
design an ordered list of specification generation steps.

Output ONLY valid JSON:
{
  "steps": [
    {
      "id": "unique_step_id",
      "name": "Human-readable step name",
      "executor": "generic" | "builtin:task_decomposer" | "builtin:context_manager" | "builtin:reviewer",
      "artifact_key": "snake_case_key" | null,
      "required": true,
      "prompt_focus": "what this step must cover (required for generic and task batches)",
      "target_count": 15
    }
  ],
  "reasoning": "brief explanation of why these steps were chosen"
}

Rules:
- Do NOT include researcher or pipeline_planner — they already ran.
- PRIMARY executor is "generic" with artifact_key + prompt_focus for each deliverable.
- Do NOT use builtin:product_analyst, builtin:architect, builtin:api_designer, builtin:ui_designer unless user explicitly requested in deliverables.
- task_decomposer steps = work packages (domain-specific phases, NOT 01-foundation/02-backend/03-frontend unless software domain).
- For education/content/hardware/embedded: NO api_spec, ui_spec, deployment_spec unless explicitly in user deliverables.
- Include task_decomposer for L2+ unless idea is documentation-only with no work breakdown.
- For L3+: include context_manager before work package steps when helpful.
- Include reviewer exactly once at the end (executor builtin:reviewer).
- target_count only on task_decomposer steps.
- Each step id MUST be unique across the pipeline.
- For L4: plan deliverables matching the domain profile + 2-6 work package batches with unique ids.
- For production maturity: plan production-ready specs (NOT MVP). Include ops, observability, rollback, compliance where domain-appropriate.
- Prefer one artifact per concern; split security/deployment into separate steps when production.
"""

DELTA_SYSTEM_PROMPT = """You are a pipeline extension planner. The specification pipeline ran once but the reviewer found gaps.
Propose ONLY NEW steps to add before the reviewer. Do not repeat steps that already exist.

Output ONLY valid JSON:
{
  "steps": [
    {
      "id": "unique_new_step_id",
      "name": "Human-readable name",
      "executor": "generic" | "builtin:task_decomposer",
      "artifact_key": "snake_case" | null,
      "required": true,
      "prompt_focus": "what to produce or which work package phase",
      "target_count": 10
    }
  ],
  "reasoning": "why these steps address reviewer gaps"
}

Rules:
- Return empty steps array if nothing meaningful to add.
- Use generic executor for missing deliverable documents.
- Use task_decomposer only for missing work breakdown with clear phase slug in prompt_focus.
- Never suggest api_designer, ui_designer, architect, product_analyst builtins.
- For production gaps add: ops, compliance, testing, manufacturing, certification — not MVP scope reduction.
"""


class PipelinePlannerAgent(BaseAgent):
    agent_id = "pipeline_planner"

    async def _execute(self, state: MultiAgentState) -> dict[str, Any]:
        session_id = state["session_id"]
        spec_level = state["spec_level"]
        rules = state["rules"]
        pipeline_cfg = rules.get("pipeline", {}) or {}
        deliverables = pipeline_cfg.get("deliverables", [])

        if pipeline_cfg.get("mode") == "fixed" or state.get("pipeline_planned"):
            return {**state, "current_agent": "supervisor"}

        await self._log(session_id, "info", "Planning dynamic specification pipeline...")

        domain = resolve_domain(state)
        maturity = resolve_spec_maturity(rules, spec_level)
        steps, reasoning = await self._plan_with_llm(state, domain, maturity)
        if not steps:
            steps = _fallback_domain_steps(spec_level, domain, maturity)
            reasoning = f"Fallback to domain profile ({domain}) for spec level {spec_level}"

        steps = merge_deliverables_into_steps(steps, deliverables)
        steps = self._apply_level_defaults(steps, spec_level, pipeline_cfg, rules, domain)
        steps = self._apply_idea_heuristics(steps, state["idea"], domain)

        await log_bus.emit(
            session_id,
            "pipeline_planned",
            {"steps": steps, "reasoning": reasoning, "domain": domain},
        )

        updated_state = {
            **state,
            "pipeline": steps,
            "pipeline_planned": True,
            "pipeline_reasoning": reasoning,
            "pipeline_version": 1,
        }
        await emit_stage_changed(
            updated_state,
            stage_id="planning",
            label="Планируем пайплайн",
            detail=f"{len(steps)} шагов · {domain}",
            agent_id="pipeline_planner",
            sub_progress=1.0,
        )

        from app.services.session import save_pipeline

        await save_pipeline(session_id, steps, reasoning)

        return {
            **updated_state,
            "agent_outputs": {**state.get("agent_outputs", {}), "pipeline_planner": reasoning},
            "current_agent": "supervisor",
        }

    async def _plan_with_llm(
        self, state: MultiAgentState, domain: str, maturity: str
    ) -> tuple[list[dict[str, Any]], str]:
        spec_level = state["spec_level"]
        rules = state["rules"]
        pipeline_cfg = rules.get("pipeline", {}) or {}
        rules_snapshot = self._rules_snapshot(state)
        agent_rules = rules.get("agent_rules", [])
        rules_text = "\n".join(
            f"- [{r.get('priority', 'medium')}] {r.get('rule', '')}" for r in agent_rules[:15]
        )
        profile = get_profile(domain)
        domain_deliverables = json.dumps(
            [
                {"key": d["artifact_key"], "focus": d["prompt_focus"]}
                for d in get_domain_deliverables(domain, maturity)
            ],
            ensure_ascii=False,
        )
        domain_packages = json.dumps(
            [
                {"id": wp["id"], "phase": wp["phase"], "focus": wp["prompt_focus"]}
                for wp in get_domain_work_packages(domain, maturity)
            ],
            ensure_ascii=False,
        )

        maturity_block = build_maturity_prompt_block(maturity, domain)
        defaults = maturity_pipeline_defaults(maturity, spec_level)
        depth_hint = ""
        if spec_level in ("L3", "L4"):
            min_steps = pipeline_cfg.get("min_steps", defaults["min_steps"])
            depth_hint = (
                f"\n{spec_level} MODE: plan at least {min_steps} steps. "
                f"Domain={domain}. Maturity={maturity}. "
                "Use domain deliverables and work packages as guide."
            )

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + maturity_block},
            {
                "role": "user",
                "content": (
                    f"Spec level: {spec_level}{depth_hint}\n"
                    f"Spec maturity: {maturity}\n"
                    f"Domain: {domain} ({profile.get('label', domain)})\n"
                    f"Idea: {state['idea']}\n"
                    f"Domain deliverable template: {domain_deliverables}\n"
                    f"Domain work packages template: {domain_packages}\n"
                    f"Include tasks hint: {pipeline_cfg.get('include_tasks')}\n"
                    f"User deliverables: {json.dumps(pipeline_cfg.get('deliverables', []))}\n"
                    f"Agent rules:\n{rules_text}\n\n{rules_snapshot}"
                ),
            },
        ]

        try:
            raw = await self._generate(state, messages)
            data = _parse_json(raw)
            if not data:
                return [], ""
            reasoning = data.get("reasoning", "Pipeline planned from idea and rules")
            steps = data.get("steps", [])
            return normalize_pipeline_steps(steps, spec_level), reasoning
        except Exception as e:
            await self._log(
                state["session_id"], "warn", f"LLM planner failed ({e}), using domain defaults"
            )
            return [], ""

    def _apply_level_defaults(
        self,
        steps: list[dict[str, Any]],
        spec_level: str,
        pipeline_cfg: dict,
        rules: dict,
        domain: str,
    ) -> list[dict[str, Any]]:
        ids = {s["id"] for s in steps}
        include_tasks = pipeline_cfg.get("include_tasks")
        if include_tasks is None:
            include_tasks = spec_level != "L1"

        has_task_step = any(step_builtin_agent_id(s) == "task_decomposer" for s in steps)
        if include_tasks and not has_task_step:
            domain_l4 = get_domain_l4_tasks_config(domain)
            default_target = (
                domain_l4["tasks_per_batch"]
                if spec_level == "L4"
                else TASK_COUNT_BY_LEVEL.get(spec_level, 20)
            )
            steps.append(
                {
                    "id": "task_decomposer",
                    "name": "Work Package Decomposition",
                    "executor": "builtin:task_decomposer",
                    "executor_agent": "task_decomposer",
                    "artifact_key": None,
                    "required": spec_level != "L1",
                    "target_count": default_target,
                    "prompt_focus": f"All work packages for domain {domain}",
                }
            )

        if spec_level in ("L2", "L3", "L4") and "reviewer" not in ids and not any(
            step_builtin_agent_id(s) == "reviewer" for s in steps
        ):
            steps.append(
                {
                    "id": "reviewer",
                    "name": "Reviewer",
                    "executor": "builtin:reviewer",
                    "executor_agent": "reviewer",
                    "artifact_key": None,
                    "required": True,
                }
            )

        if spec_level in ("L3", "L4") and "context_manager" not in ids and not any(
            step_builtin_agent_id(s) == "context_manager" for s in steps
        ):
            insert_at = next(
                (
                    i
                    for i, s in enumerate(steps)
                    if step_builtin_agent_id(s) == "task_decomposer"
                ),
                len(steps),
            )
            steps.insert(
                insert_at,
                {
                    "id": "context_manager",
                    "name": "Context Manager",
                    "executor": "builtin:context_manager",
                    "executor_agent": "context_manager",
                    "artifact_key": None,
                    "required": False,
                },
            )

        maturity = resolve_spec_maturity(rules, spec_level)
        defaults = maturity_pipeline_defaults(maturity, spec_level)

        if spec_level in ("L3", "L4"):
            l4_cfg = rules.get("l4", {}) or {}
            min_deliverables = pipeline_cfg.get("min_deliverables", defaults["min_deliverables"])
            min_steps = pipeline_cfg.get("min_steps", defaults["min_steps"])
            tasks_per_batch = l4_cfg.get("tasks_per_batch") or get_domain_l4_tasks_config(domain)[
                "tasks_per_batch"
            ]
            if maturity in ("production", "enterprise"):
                tasks_per_batch = max(tasks_per_batch, defaults["tasks_per_batch"])

            steps = expand_prod_deliverables(steps, domain, maturity)
            steps = ensure_domain_deliverables(steps, domain, min_deliverables, maturity)
            if include_tasks:
                steps = ensure_domain_work_packages(steps, domain, tasks_per_batch, maturity)

            existing_keys = {s.get("artifact_key") for s in steps if s.get("artifact_key")}
            fillers_needed = max(0, min_steps - len(steps))
            if fillers_needed:
                for filler in named_prod_fillers(domain, maturity, existing_keys, fillers_needed):
                    steps.insert(max(len(steps) - 1, 0), filler)

            while len(steps) < min_steps:
                extra_id = f"generic_extra_{len(steps)}"
                if any(s.get("id") == extra_id for s in steps):
                    break
                steps.insert(
                    max(len(steps) - 1, 0),
                    {
                        "id": extra_id,
                        "name": f"Additional Specification {len(steps)}",
                        "executor": "generic",
                        "artifact_key": extra_id,
                        "required": False,
                        "prompt_focus": "Additional domain-specific production detail not covered elsewhere",
                    },
                )

        return steps

    def _apply_idea_heuristics(
        self, steps: list[dict[str, Any]], idea: str, domain: str
    ) -> list[dict[str, Any]]:
        if domain != "software":
            web_keys = {"api_spec", "ui_spec", "deployment_spec", "observability_spec"}
            steps = [
                s
                for s in steps
                if s.get("artifact_key") not in web_keys
                and s.get("id") not in ("api_designer", "ui_designer", "architect", "product_analyst")
                and step_builtin_agent_id(s) not in ("api_designer", "ui_designer")
            ]
        return steps


async def plan_pipeline_delta(
    state: MultiAgentState,
    llm_provider: Any,
    reviewer_report: dict[str, Any],
) -> tuple[list[dict[str, Any]], str]:
    """Plan additional pipeline steps from reviewer gaps."""
    session_id = state["session_id"]
    rules = state.get("rules", {})
    domain = resolve_domain(state)
    maturity = resolve_spec_maturity(rules, state.get("spec_level", "L2"))
    pipeline = state.get("pipeline") or []
    existing_ids = {s.get("id") for s in pipeline}
    existing_keys = {s.get("artifact_key") for s in pipeline if s.get("artifact_key")}
    artifacts = state.get("artifacts", {})
    issues = reviewer_report.get("issues", [])

    missing_keys: set[str] = set()
    for issue in issues:
        loc = issue.get("location", "")
        key = loc.split("#")[0].split("/")[-1].replace(".md", "") if loc else ""
        if key and key not in artifacts and key not in existing_keys:
            missing_keys.add(key)
        desc = issue.get("description", "").lower()
        if "missing" in desc or "отсутств" in desc:
            for d in get_domain_deliverables(domain, maturity):
                ak = d["artifact_key"]
                if ak in desc and ak not in artifacts and ak not in existing_keys:
                    missing_keys.add(ak)

    issues_text = json.dumps(issues[:20], ensure_ascii=False)
    artifacts_text = json.dumps(list(artifacts.keys()), ensure_ascii=False)
    pipeline_text = json.dumps(
        [{"id": s["id"], "artifact_key": s.get("artifact_key")} for s in pipeline],
        ensure_ascii=False,
    )
    prior_summary = ""
    try:
        prior_summary = await summarize_artifacts(session_id, max_per_key=400)
    except Exception:
        prior_summary = ""

    agent = PipelinePlannerAgent(llm=llm_provider)
    maturity_block = build_maturity_prompt_block(maturity, domain)
    messages = [
        {"role": "system", "content": DELTA_SYSTEM_PROMPT + "\n\n" + maturity_block},
        {
            "role": "user",
            "content": (
                f"Domain: {domain}\n"
                f"Idea: {state.get('idea', '')}\n"
                f"Existing pipeline steps: {pipeline_text}\n"
                f"Artifacts already produced: {artifacts_text}\n"
                f"Reviewer issues: {issues_text}\n"
                f"Likely missing deliverables: {sorted(missing_keys)}\n"
                f"Prior spec summary:\n{prior_summary[:3000]}"
            ),
        },
    ]
    try:
        raw = await agent._generate(state, messages)
        data = _parse_json(raw) or {}
        reasoning = data.get("reasoning", "Delta pipeline extension")
        new_steps = normalize_pipeline_steps(data.get("steps", []), state.get("spec_level", "L2"))
        new_steps = [s for s in new_steps if s.get("id") not in existing_ids]
        if not new_steps and missing_keys:
            for key in sorted(missing_keys):
                step_id = f"delta_{key}"
                if step_id in existing_ids:
                    continue
                profile_match = next(
                    (d for d in get_domain_deliverables(domain) if d["artifact_key"] == key),
                    None,
                )
                new_steps.append(
                    {
                        "id": step_id,
                        "name": profile_match["name"] if profile_match else key.replace("_", " ").title(),
                        "executor": "generic",
                        "artifact_key": key,
                        "required": True,
                        "prompt_focus": (
                            profile_match["prompt_focus"]
                            if profile_match
                            else f"Address reviewer gap for {key}"
                        ),
                    }
                )
        return new_steps, reasoning
    except Exception:
        fallback: list[dict[str, Any]] = []
        for key in sorted(missing_keys):
            step_id = f"delta_{key}"
            if step_id not in existing_ids:
                fallback.append(
                    {
                        "id": step_id,
                        "name": key.replace("_", " ").title(),
                        "executor": "generic",
                        "artifact_key": key,
                        "required": True,
                        "prompt_focus": f"Produce missing deliverable {key} per reviewer feedback",
                    }
                )
        return fallback, "Heuristic delta from missing artifact keys"


def resolve_domain(state: MultiAgentState) -> str:
    rules = state.get("rules", {})
    declared = rules.get("project", {}).get("domain", "general")
    if isinstance(declared, str):
        declared = normalize_domain(declared)
    else:
        declared = str(declared)
    return detect_domain(state.get("idea", ""), declared)


def apply_domain_l4_rules(rules: dict[str, Any]) -> dict[str, Any]:
    """Adjust L4 min_tasks/tasks_per_batch from domain profile and maturity."""
    if rules.get("spec_level") != "L4":
        return rules
    rules = dict(rules)
    domain = normalize_domain(rules.get("project", {}).get("domain", "general"))
    maturity = resolve_spec_maturity(rules, "L4")
    defaults = maturity_pipeline_defaults(maturity, "L4")
    cfg = get_domain_l4_tasks_config(domain)
    l4 = dict(rules.get("l4") or {})
    if l4.get("min_tasks", 100) == 100 and domain != "software":
        l4["min_tasks"] = cfg["min_tasks"]
    elif maturity in ("production", "enterprise"):
        l4["min_tasks"] = max(int(l4.get("min_tasks", 100)), int(cfg["min_tasks"] * 1.2))
    if domain != "software" and l4.get("tasks_per_batch", 25) == 25:
        l4["tasks_per_batch"] = cfg["tasks_per_batch"]
    elif maturity in ("production", "enterprise"):
        l4["tasks_per_batch"] = max(int(l4.get("tasks_per_batch", 25)), defaults["tasks_per_batch"])
    pipeline = dict(rules.get("pipeline") or {})
    if pipeline.get("max_replan_cycles", 2) < defaults["max_replan_cycles"]:
        pipeline["max_replan_cycles"] = defaults["max_replan_cycles"]
    rules["pipeline"] = pipeline
    rules["l4"] = l4
    return rules


def _fallback_domain_steps(spec_level: str, domain: str, maturity: str = "mvp") -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for d in get_domain_deliverables(domain, maturity):
        steps.append(
            {
                "id": d["id"],
                "name": d["name"],
                "executor": "generic",
                "artifact_key": d["artifact_key"],
                "required": d.get("required", True),
                "prompt_focus": d["prompt_focus"],
            }
        )
    if spec_level != "L1":
        steps.extend(
            work_packages_to_pipeline_steps(get_domain_work_packages(domain, maturity))
        )
    if spec_level in ("L2", "L3", "L4"):
        steps.append(
            {
                "id": "reviewer",
                "name": "Reviewer",
                "executor": "builtin:reviewer",
                "executor_agent": "reviewer",
                "artifact_key": None,
                "required": True,
            }
        )
    return steps


def _parse_json(raw: str) -> dict | None:
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
