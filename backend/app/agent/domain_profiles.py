"""Domain profiles — deliverables and work packages per project domain."""

from __future__ import annotations

from typing import Any, Literal

DomainType = Literal["general", "software", "education", "embedded", "hardware", "content"]

VALID_DOMAINS: frozenset[str] = frozenset(
    {"general", "software", "education", "embedded", "hardware", "content"}
)

DOMAIN_DETECT_KEYWORDS: dict[str, list[str]] = {
    "education": [
        "умк",
        "учебн",
        "курс",
        "lesson",
        "curriculum",
        "методич",
        "обучен",
        "training material",
        "lms content",
    ],
    "embedded": [
        "embedded",
        "raspberry pi",
        "arduino",
        "fpv",
        "дрон",
        "drone",
        "autopilot",
        "микроконтроллер",
        "firmware",
        "rtos",
    ],
    "hardware": [
        "pcb",
        "схем",
        "hardware design",
        "bom",
        "печатн",
        "электрон",
    ],
    "content": [
        "статья",
        "блог",
        "контент",
        "publication",
        "editorial",
        "copywriting",
    ],
    "software": [
        "api",
        "backend",
        "frontend",
        "saas",
        "web app",
        "микросервис",
        "fastapi",
        "react",
        "postgres",
    ],
}


def normalize_domain(domain: str | None) -> DomainType:
    if domain and domain in VALID_DOMAINS:
        return domain  # type: ignore[return-value]
    return "general"


def detect_domain(idea: str, declared: str | None = None) -> DomainType:
    """Resolve domain: explicit rules value wins unless 'general', then heuristic from idea."""
    if declared and declared != "general" and declared in VALID_DOMAINS:
        return declared  # type: ignore[return-value]

    idea_lower = idea.lower()
    scores: dict[str, int] = {d: 0 for d in VALID_DOMAINS if d != "general"}
    for domain, keywords in DOMAIN_DETECT_KEYWORDS.items():
        for kw in keywords:
            if kw in idea_lower:
                scores[domain] = scores.get(domain, 0) + 1

    best = max(scores.items(), key=lambda x: x[1], default=("general", 0))
    if best[1] > 0:
        return best[0]  # type: ignore[return-value]
    if declared and declared in VALID_DOMAINS:
        return declared  # type: ignore[return-value]
    return "general"


def _d(
    artifact_key: str,
    name: str,
    prompt_focus: str,
    *,
    required: bool = True,
) -> dict[str, Any]:
    return {
        "id": artifact_key,
        "name": name,
        "artifact_key": artifact_key,
        "prompt_focus": prompt_focus,
        "required": required,
    }


def _wp(
    wp_id: str,
    name: str,
    phase: str,
    prompt_focus: str,
    target_count: int = 25,
) -> dict[str, Any]:
    return {
        "id": wp_id,
        "name": name,
        "phase": phase,
        "prompt_focus": prompt_focus,
        "target_count": target_count,
    }


DOMAIN_PROFILES: dict[str, dict[str, Any]] = {
    "software": {
        "label": "Software / Web",
        "min_tasks": 100,
        "tasks_per_batch": 25,
        "review_checklist": [
            "product_spec defines scope and users",
            "architecture_spec covers system design",
            "security and test strategy present",
            "tasks grouped by work phase not random",
        ],
        "deliverables": [
            _d("product_spec", "Product Specification", "Scope, users, production boundaries and use cases (not MVP)"),
            _d(
                "architecture_spec",
                "Architecture Specification",
                "System context, components, ADRs, deployment overview",
            ),
            _d("api_spec", "API Specification", "Endpoints, schemas, auth, error handling"),
            _d("security_spec", "Security Specification", "Threat model, authn/authz, data protection"),
            _d("data_model", "Data Model", "Entities, relationships, lifecycle"),
            _d("test_strategy", "Test Strategy", "Unit, integration, e2e, CI gates"),
            _d("deployment_spec", "Deployment Specification", "Environments, CI/CD, rollout"),
            _d("risk_register", "Risk Register", "Technical risks, mitigations, owners"),
        ],
        "prod_deliverables": [
            _d("operational_spec", "Operational Specification", "Runbooks, on-call, incident response, escalation"),
            _d("observability_spec", "Observability Specification", "Metrics, logs, traces, alerts, dashboards"),
            _d("sla_spec", "SLA / SLO Specification", "SLO targets, error budgets, availability commitments"),
            _d("dr_spec", "Disaster Recovery Specification", "Backup, DR, RTO/RPO, failover procedures"),
            _d("compliance_spec", "Compliance Specification", "GDPR/152-FZ, audit trail, data handling (if applicable)"),
            _d("threat_model", "Threat Model", "STRIDE or equivalent threat analysis"),
            _d("security_controls", "Security Controls", "Controls mapped to threats, implementation requirements"),
            _d("cicd_spec", "CI/CD Specification", "Pipelines, gates, artifact promotion"),
            _d("environment_spec", "Environment Specification", "Dev/stage/prod parity, secrets, config management"),
        ],
        "prod_work_packages": [
            _wp("wp_hardening", "Work Package: Hardening", "05-hardening", "Security hardening, perf, chaos/resilience tests", 20),
            _wp("wp_ops", "Work Package: Operations", "06-ops", "Monitoring, runbooks, on-call, incident drills", 20),
            _wp("wp_compliance", "Work Package: Compliance", "07-compliance", "Audit, compliance checks, documentation", 15),
        ],
        "prod_review_checklist": [
            "Observability and rollback documented",
            "No MVP-only scope without [DEFERRED]",
            "SLA/SLO or availability targets stated",
        ],
        "enterprise_deliverables": [
            _d("audit_spec", "Audit Specification", "Audit trail, access logging, compliance evidence"),
        ],
        "work_packages": [
            _wp(
                "wp_design",
                "Work Package: Design",
                "01-design",
                "Design phase only: requirements refinement, architecture decisions, API contracts",
            ),
            _wp(
                "wp_implementation",
                "Work Package: Implementation",
                "02-implementation",
                "Implementation phase only: core services, data layer, business logic",
            ),
            _wp(
                "wp_integration",
                "Work Package: Integration",
                "03-integration",
                "Integration phase: third-party services, E2E wiring, deployment prep",
            ),
            _wp(
                "wp_release",
                "Work Package: Release",
                "04-release",
                "Release phase: hardening, monitoring, documentation, launch checklist",
            ),
        ],
    },
    "education": {
        "label": "Education / UMK",
        "min_tasks": 20,
        "tasks_per_batch": 8,
        "review_checklist": [
            "product_spec is a TZ for educational materials not a software product",
            "course_structure or lesson_plan present",
            "theoretical_materials and practical_tasks aligned",
            "assessment_system with rubrics",
            "no requirements for LMS/API/UI development unless explicitly requested",
        ],
        "deliverables": [
            _d("product_spec", "Technical Assignment (TZ)", "TZ for UMK: goals, audience, scope, acceptance criteria"),
            _d(
                "course_structure",
                "Course Structure",
                "Modules, sequence, hours, learning outcomes, dependencies",
            ),
            _d("lesson_plan", "Lesson Plan", "Calendar-thematic plan, session templates"),
            _d(
                "theoretical_materials",
                "Theoretical Materials",
                "Lecture content, examples, self-check questions",
            ),
            _d("practical_tasks", "Practical Tasks", "Exercises with hints and solution outlines"),
            _d("assessment_system", "Assessment System", "Tests, rubrics, grading weights"),
            _d("methodical_materials", "Methodical Guide", "Instructor notes, timing, common questions"),
            _d("additional_materials", "Additional Materials", "Glossary, references, handouts"),
        ],
        "work_packages": [
            _wp(
                "wp_design",
                "Work Package: Design",
                "01-design",
                "Design phase: TZ, module structure, content model, lesson plan outline",
                8,
            ),
            _wp(
                "wp_content",
                "Work Package: Content",
                "02-content",
                "Content authoring: theory modules, examples, instructor notes",
                8,
            ),
            _wp(
                "wp_practice",
                "Work Package: Practice",
                "03-practice",
                "Practice phase: exercises, student projects, rubrics",
                8,
            ),
            _wp(
                "wp_review",
                "Work Package: Review",
                "04-review",
                "Review phase: pilot plan, quality checklist, revision tasks",
                6,
            ),
        ],
    },
    "embedded": {
        "label": "Embedded / IoT",
        "min_tasks": 40,
        "tasks_per_batch": 15,
        "review_checklist": [
            "requirements_spec covers hardware and software boundaries",
            "safety_spec addresses real-time and failure modes",
            "hardware_interface documents sensors/actuators",
        ],
        "deliverables": [
            _d("requirements_spec", "Requirements Specification", "Functional and non-functional requirements"),
            _d(
                "system_architecture",
                "System Architecture",
                "Block diagram, components, data flows, timing constraints",
            ),
            _d(
                "hardware_interface",
                "Hardware Interface Specification",
                "GPIO, buses, sensors, actuators, pin maps",
            ),
            _d("safety_spec", "Safety Specification", "Fail-safe behavior, watchdogs, limits"),
            _d("test_plan", "Test Plan", "Unit, HIL, field validation procedures"),
            _d("risk_register", "Risk Register", "Technical risks and mitigations"),
        ],
        "prod_deliverables": [
            _d("certification_plan", "Certification Plan", "Field trials, certification, acceptance test matrix"),
            _d("ota_update_spec", "OTA Update Specification", "Firmware update, rollback, signing, staging"),
            _d("manufacturing_spec", "Manufacturing Specification", "Line calibration, QC, traceability"),
            _d("maintenance_spec", "Maintenance Specification", "Service, component replacement, MTBF, spare parts"),
        ],
        "prod_work_packages": [
            _wp("wp_certification", "Work Package: Certification", "05-certification", "Certification tests, field trials, sign-off", 15),
            _wp("wp_manufacturing", "Work Package: Manufacturing", "06-manufacturing", "Production calibration, QC fixtures, traceability", 15),
            _wp("wp_field_ops", "Work Package: Field Operations", "07-field-ops", "Deployment, maintenance, remote diagnostics", 15),
        ],
        "prod_review_checklist": [
            "OTA or update strategy documented",
            "Manufacturing/calibration addressed",
            "Field validation and certification covered",
        ],
        "work_packages": [
            _wp("wp_bringup", "Work Package: Bring-up", "01-bringup", "Board bring-up, drivers, basic I/O", 12),
            _wp(
                "wp_control",
                "Work Package: Control Loop",
                "02-control",
                "Control algorithms, real-time tasks, tuning",
                12,
            ),
            _wp(
                "wp_integration",
                "Work Package: Integration",
                "03-integration",
                "Sensor fusion, communication, system integration",
                12,
            ),
            _wp(
                "wp_validation",
                "Work Package: Validation",
                "04-validation",
                "Testing, calibration, safety validation",
                12,
            ),
        ],
    },
    "hardware": {
        "label": "Hardware",
        "min_tasks": 30,
        "tasks_per_batch": 12,
        "review_checklist": [
            "requirements cover electrical and mechanical constraints",
            "block_diagram and bom_spec present",
            "test_protocol defines verification steps",
        ],
        "deliverables": [
            _d("requirements_spec", "Requirements Specification", "Electrical, mechanical, environmental requirements"),
            _d("block_diagram", "Block Diagram", "System blocks, interfaces, power domains"),
            _d("bom_spec", "BOM Specification", "Components, alternatives, sourcing notes"),
            _d("test_protocol", "Test Protocol", "Bench tests, acceptance criteria"),
            _d("risk_register", "Risk Register", "Design risks and mitigations"),
        ],
        "prod_deliverables": [
            _d("dfm_spec", "DFM Specification", "Design for manufacturing, tolerances, assembly"),
            _d("environmental_qual", "Environmental Qualification", "Temperature, humidity, EMC test requirements"),
            _d("production_test_spec", "Production Test Specification", "ATE, fixtures, yield criteria"),
            _d("field_service_spec", "Field Service Specification", "Repair, replacement, service intervals"),
        ],
        "prod_work_packages": [
            _wp("wp_qualification", "Work Package: Qualification", "04-qualification", "Environmental and compliance testing", 12),
            _wp("wp_production", "Work Package: Production", "05-production", "Manufacturing ramp, test fixtures, yield", 12),
        ],
        "prod_review_checklist": [
            "DFM and production test defined",
            "Environmental qualification addressed",
        ],
        "work_packages": [
            _wp("wp_design", "Work Package: Design", "01-design", "Schematic, layout planning, component selection", 10),
            _wp("wp_prototype", "Work Package: Prototype", "02-prototype", "Prototype build, bring-up, measurements", 10),
            _wp(
                "wp_verification",
                "Work Package: Verification",
                "03-verification",
                "Verification tests, rework, documentation",
                10,
            ),
        ],
    },
    "content": {
        "label": "Content / Editorial",
        "min_tasks": 24,
        "tasks_per_batch": 8,
        "review_checklist": [
            "brief defines audience and tone",
            "outline and draft are consistent",
            "style_guide applied",
        ],
        "deliverables": [
            _d("content_brief", "Content Brief", "Audience, goals, tone, constraints"),
            _d("outline", "Outline", "Structure, sections, key messages"),
            _d("draft", "Draft", "Full draft content"),
            _d("style_guide", "Style Guide", "Voice, terminology, formatting rules"),
            _d("publication_plan", "Publication Plan", "Channels, schedule, review workflow"),
        ],
        "work_packages": [
            _wp("wp_research", "Work Package: Research", "01-research", "Research and source gathering tasks", 8),
            _wp("wp_writing", "Work Package: Writing", "02-writing", "Drafting and revision tasks", 8),
            _wp("wp_editing", "Work Package: Editing", "03-editing", "Editing, fact-check, polish", 8),
            _wp("wp_qa", "Work Package: QA", "04-qa", "Final QA and publication prep", 6),
        ],
    },
    "general": {
        "label": "General",
        "min_tasks": 40,
        "tasks_per_batch": 15,
        "review_checklist": [
            "scope_spec defines boundaries",
            "structure_spec organizes deliverables",
            "quality_plan defines acceptance",
        ],
        "deliverables": [
            _d("scope_spec", "Scope Specification", "Goals, boundaries, stakeholders, constraints"),
            _d("structure_spec", "Structure Specification", "Organization of work products and dependencies"),
            _d("quality_plan", "Quality Plan", "Acceptance criteria, review process"),
            _d("risk_register", "Risk Register", "Risks and mitigations"),
        ],
        "work_packages": [
            _wp("wp_phase_1", "Work Package: Phase 1", "01-phase-1", "Phase 1 work items from specifications", 15),
            _wp("wp_phase_2", "Work Package: Phase 2", "02-phase-2", "Phase 2 work items from specifications", 15),
            _wp("wp_phase_3", "Work Package: Phase 3", "03-phase-3", "Phase 3 work items from specifications", 15),
        ],
    },
}


def get_profile(domain: str | None) -> dict[str, Any]:
    return DOMAIN_PROFILES.get(normalize_domain(domain), DOMAIN_PROFILES["general"])


def get_domain_deliverables(domain: str | None, maturity: str | None = None) -> list[dict[str, Any]]:
    profile = get_profile(domain)
    base = list(profile.get("deliverables", []))
    from app.agent.spec_maturity import is_production_maturity

    if maturity and is_production_maturity(maturity):
        seen = {d["artifact_key"] for d in base}
        for d in profile.get("prod_deliverables", []):
            if d["artifact_key"] not in seen:
                base.append(d)
                seen.add(d["artifact_key"])
        if maturity == "enterprise":
            for d in profile.get("enterprise_deliverables", []):
                if d["artifact_key"] not in seen:
                    base.append(d)
    return base


def get_domain_work_packages(domain: str | None, maturity: str | None = None) -> list[dict[str, Any]]:
    profile = get_profile(domain)
    base = list(profile.get("work_packages", []))
    from app.agent.spec_maturity import is_production_maturity

    if maturity and is_production_maturity(maturity):
        seen = {wp["id"] for wp in base}
        for wp in profile.get("prod_work_packages", []):
            if wp["id"] not in seen:
                base.append(wp)
                seen.add(wp["id"])
    return base


def get_domain_review_checklist(domain: str | None, maturity: str | None = None) -> list[str]:
    profile = get_profile(domain)
    items = list(profile.get("review_checklist", []))
    if maturity:
        from app.agent.spec_maturity import build_maturity_review_checklist, is_production_maturity

        if is_production_maturity(maturity):
            items.extend(profile.get("prod_review_checklist", []))
        items.extend(build_maturity_review_checklist(maturity, normalize_domain(domain)))
    return items


def get_domain_l4_tasks_config(domain: str | None) -> dict[str, int]:
    profile = get_profile(domain)
    return {
        "min_tasks": int(profile.get("min_tasks", 40)),
        "tasks_per_batch": int(profile.get("tasks_per_batch", 15)),
    }


def work_packages_to_pipeline_steps(
    work_packages: list[dict[str, Any]],
    *,
    tasks_per_batch_override: int | None = None,
) -> list[dict[str, Any]]:
    """Convert domain work packages to pipeline task_decomposer steps."""
    steps: list[dict[str, Any]] = []
    for wp in work_packages:
        target = tasks_per_batch_override or wp.get("target_count", 15)
        steps.append(
            {
                "id": wp["id"],
                "name": wp["name"],
                "executor": "builtin:task_decomposer",
                "executor_agent": "task_decomposer",
                "artifact_key": None,
                "required": True,
                "target_count": target,
                "prompt_focus": (
                    f"Work package phase '{wp.get('phase', 'work')}': {wp.get('prompt_focus', '')}. "
                    f"Use phase slug '{wp.get('phase', 'work')}' for all tasks in this batch."
                ),
                "work_package_phase": wp.get("phase"),
            }
        )
    return steps
