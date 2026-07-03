"""Spec maturity (MVP vs production) — resolution, prompts, pipeline defaults."""

from __future__ import annotations

from typing import Any, Literal

SpecMaturityType = Literal["mvp", "production", "enterprise"]

MATURITY_ORDER = {"mvp": 0, "production": 1, "enterprise": 2}

DEFAULT_BY_SPEC_LEVEL: dict[str, SpecMaturityType] = {
    "L1": "mvp",
    "L2": "mvp",
    "L3": "production",
    "L4": "production",
}


def resolve_spec_maturity(rules: dict[str, Any], spec_level: str | None = None) -> SpecMaturityType:
    """Resolve effective maturity from rules.project.spec_maturity and spec_level."""
    level = spec_level or str(rules.get("spec_level", "L2"))
    project = rules.get("project") or {}
    declared = project.get("spec_maturity")
    if declared in MATURITY_ORDER:
        return declared  # type: ignore[return-value]
    return DEFAULT_BY_SPEC_LEVEL.get(level, "mvp")


def is_production_maturity(maturity: str) -> bool:
    return MATURITY_ORDER.get(maturity, 0) >= MATURITY_ORDER["production"]


def maturity_pipeline_defaults(maturity: str, spec_level: str) -> dict[str, int]:
    """Pipeline/L4 numeric defaults scaled by maturity and spec level."""
    base = {
        "min_steps": 8,
        "min_deliverables": 6,
        "tasks_per_batch": 15,
        "max_replan_cycles": 2,
        "min_tasks_multiplier": 100,
    }
    if spec_level == "L3":
        base.update(min_steps=14, min_deliverables=10, tasks_per_batch=20, max_replan_cycles=3)
    elif spec_level == "L4":
        base.update(min_steps=12, min_deliverables=8, tasks_per_batch=20, max_replan_cycles=2)

    if is_production_maturity(maturity):
        if spec_level == "L3":
            base.update(
                min_steps=18,
                min_deliverables=12,
                tasks_per_batch=22,
                max_replan_cycles=3,
                min_tasks_multiplier=120,
            )
        elif spec_level == "L4":
            base.update(
                min_steps=22,
                min_deliverables=14,
                tasks_per_batch=25,
                max_replan_cycles=4,
                min_tasks_multiplier=140,
            )

    if maturity == "enterprise":
        base["min_steps"] = base["min_steps"] + 2
        base["min_deliverables"] = base["min_deliverables"] + 2
        base["max_replan_cycles"] = min(base["max_replan_cycles"] + 1, 10)

    return base


def build_maturity_prompt_block(maturity: str, domain: str) -> str:
    """Shared instruction block injected into agent prompts."""
    if maturity == "mvp":
        return (
            "SPEC MATURITY: MVP / brief scope.\n"
            "- Focus on core scope and near-term delivery.\n"
            "- Defer non-essential ops/compliance with explicit [DEFERRED] markers.\n"
        )

    enterprise_extra = ""
    if maturity == "enterprise":
        enterprise_extra = (
            "- Enterprise: include compliance, audit trail, data residency, and vendor SLAs where applicable.\n"
        )

    domain_hints = {
        "software": "Include SLO/SLA, observability, CI/CD rollback, DR, runbooks, security hardening.",
        "embedded": "Include OTA, manufacturing QC, field trials, certification, maintenance, fail-safe validation.",
        "hardware": "Include DFM, environmental qualification, production test, field service.",
        "education": "Include pilot rollout, instructor training, quality assurance, revision governance.",
        "content": "Include editorial QA, fact-check workflow, publication governance.",
        "general": "Include operational readiness, quality gates, and maintenance.",
    }
    hint = domain_hints.get(domain, domain_hints["general"])

    return (
        f"SPEC MATURITY: {maturity.upper()} (production-ready, NOT MVP).\n"
        "- Do NOT scope as MVP, prototype-only, or 'phase 1' unless marked [DEFERRED].\n"
        "- Avoid phrases like 'later', 'in the first version', 'future work' without [DEFERRED].\n"
        "- Cover: SLO/availability, failure modes, security, rollout/rollback, maintenance, prod-like testing.\n"
        f"- Domain focus ({domain}): {hint}\n"
        "- Tasks must include hardening, validation, and ops — not only happy-path development.\n"
        f"{enterprise_extra}"
    )


def build_maturity_review_checklist(maturity: str, domain: str) -> list[str]:
    """Additional reviewer checklist items for production maturity."""
    if not is_production_maturity(maturity):
        return []
    items = [
        "No MVP-only scope without explicit [DEFERRED] markers",
        "Observability or operational readiness documented (domain-appropriate)",
        "Rollback, failure modes, or fail-safe behavior addressed",
        "NFR from rules.nfr reflected in specifications",
        "Specs describe deployable/production operation, not prototype demo only",
    ]
    if domain == "software":
        items.extend(
            [
                "SLA/SLO or availability targets stated",
                "Security and deployment/rollback covered",
            ]
        )
    elif domain == "embedded":
        items.extend(
            [
                "OTA or update strategy documented if firmware involved",
                "Manufacturing/calibration or field validation addressed",
            ]
        )
    if maturity == "enterprise":
        items.append("Compliance and audit requirements addressed where applicable")
    return items


def build_intake_maturity_hint(spec_level: str, maturity: str) -> str:
    """Extra intake guidance for L3/L4 production sessions."""
    if spec_level not in ("L3", "L4") or not is_production_maturity(maturity):
        return ""
    return (
        "This is a production-grade specification (not MVP). "
        "If the idea lacks: deployment target (cloud/on-prem/edge), availability/SLO expectations, "
        "regulatory/compliance constraints, or maintenance/ops requirements — ask about them. "
        "Do NOT ask about MVP scope reduction."
    )
