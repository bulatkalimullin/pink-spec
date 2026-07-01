"""Export session artifacts to output/{session_id}/ and ZIP bundle."""

from __future__ import annotations

import json
import zipfile
from io import BytesIO
from pathlib import Path

import structlog

from app.config import get_settings

logger = structlog.get_logger(__name__)

OUTPUT_ROOT = Path(get_settings().output_path)

ARTIFACT_EXT_MAP = {
    "api_spec": "openapi.yaml",
    "manifest": "json",
}


def session_output_dir(session_id: str) -> Path:
    path = OUTPUT_ROOT / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def docs_dir(session_id: str) -> Path:
    path = session_output_dir(session_id) / "docs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def artifact_filename(artifact_type: str) -> str:
    ext = ARTIFACT_EXT_MAP.get(artifact_type, "md")
    return f"{artifact_type}.{ext}"


def artifact_manifest_path(artifact_type: str) -> str:
    return f"docs/{artifact_filename(artifact_type)}"


def write_artifact(session_id: str, artifact_type: str, content: str) -> Path:
    filename = artifact_filename(artifact_type)
    path = docs_dir(session_id) / filename
    path.write_text(content, encoding="utf-8")
    return path


def write_manifest(session_id: str, manifest: dict) -> Path:
    path = session_output_dir(session_id) / "manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def write_gaps(session_id: str, gaps: dict) -> Path:
    lines = [
        "# Gaps & Recovery Report\n",
        f"## Session\n- status: {gaps.get('status', 'unknown')}\n- reason: {gaps.get('reason', 'unknown')}\n",
        "## Failed / Skipped Steps\n",
    ]
    for step in gaps.get("failed_steps", []):
        lines.append(f"- [{step.get('agent', '?')}] {step.get('reason', '')}\n")
    lines.append("\n## Unresolved Questions\n")
    for q in gaps.get("open_questions", []):
        lines.append(f"- {q}\n")
    lines.append("\n## Manual Follow-up\n")
    for i, action in enumerate(gaps.get("manual_actions", []), 1):
        lines.append(f"{i}. {action}\n")

    content = "".join(lines)
    path = session_output_dir(session_id) / "gaps.md"
    path.write_text(content, encoding="utf-8")
    return path


def write_task(session_id: str, task: dict) -> Path:
    phase = task.get("phase", "00-unknown")
    task_id = task.get("id", "000")
    slug = task.get("slug", task.get("title", "task").lower().replace(" ", "-")[:40])
    filename = f"{task_id}-{slug}.md"
    tasks_dir = session_output_dir(session_id) / "tasks" / f"phase-{phase}"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    path = tasks_dir / filename
    content = _render_task(task)
    path.write_text(content, encoding="utf-8")
    return path


def write_task_index(session_id: str, tasks: list[dict]) -> Path:
    lines = ["# Task Index\n", f"Total tasks: {len(tasks)}\n\n"]
    phases: dict[str, list[dict]] = {}
    for t in tasks:
        phase = t.get("phase", "00-unknown")
        phases.setdefault(phase, []).append(t)

    for phase in sorted(phases.keys()):
        lines.append(f"## Phase {phase}\n\n")
        for t in sorted(phases[phase], key=lambda x: x.get("id", "")):
            task_id = t.get("id", "000")
            slug = t.get("slug", t.get("title", "task").lower().replace(" ", "-")[:40])
            title = t.get("title", "Task")
            rel = f"phase-{phase}/{task_id}-{slug}.md"
            lines.append(f"- [{task_id} {title}](../tasks/{rel})\n")
        lines.append("\n")

    path = session_output_dir(session_id) / "tasks" / "TASK_INDEX.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")
    return path


def write_task_roadmap(session_id: str, content: str) -> Path:
    path = docs_dir(session_id) / "TASK_ROADMAP.md"
    path.write_text(content, encoding="utf-8")
    return path


def _render_task(task: dict) -> str:
    depends = ", ".join(f'"{d}"' for d in task.get("depends_on", []))
    spec_refs = "\n".join(f'  - "{r}"' for r in task.get("spec_refs", []))
    steps = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(task.get("steps", [])))
    criteria = "\n".join(f"- [ ] {c}" for c in task.get("acceptance_criteria", []))
    notes = "\n".join(f"- {n}" for n in task.get("notes", []))

    return f"""---
id: "{task.get("id", "000")}"
phase: "{task.get("phase", "")}"
title: "{task.get("title", "")}"
priority: {task.get("priority", "medium")}
estimated_minutes: {task.get("estimated_minutes", 30)}
depends_on: [{depends}]
spec_refs:
{spec_refs or "  []"}
status: todo
---

## Goal

{task.get("goal", "")}

## Context

{task.get("context", "")}

## Steps

{steps}

## Acceptance Criteria

{criteria}

## Notes / Pitfalls

{notes or "N/A"}

## Verification

{task.get("verification", "Manual review.")}
"""


def resolve_artifact_path(
    session_id: str,
    artifact_type: str,
    manifest: dict | None = None,
) -> Path | None:
    output_dir = session_output_dir(session_id)
    artifacts = (manifest or {}).get("artifacts") or {}
    if filename := artifacts.get(artifact_type):
        for base in (output_dir, docs_dir(session_id)):
            path = base / filename.replace("docs/", "") if "docs/" in filename else base / filename
            if not path.is_file() and "/" in filename:
                path = output_dir / filename
            if path.is_file():
                return path

    ext = ARTIFACT_EXT_MAP.get(artifact_type, "md")
    candidates = [
        docs_dir(session_id) / f"{artifact_type}.{ext}",
        docs_dir(session_id) / f"{artifact_type}.md",
        docs_dir(session_id) / f"{artifact_type}.openapi.yaml",
        output_dir / f"{artifact_type}.{ext}",
        output_dir / f"{artifact_type}.md",
        output_dir / f"{artifact_type}.openapi.yaml",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def read_artifact(
    session_id: str,
    artifact_type: str,
    manifest: dict | None = None,
) -> tuple[str, str]:
    path = resolve_artifact_path(session_id, artifact_type, manifest)
    if path is None:
        raise FileNotFoundError(f"Artifact not found: {artifact_type}")
    content = path.read_text(encoding="utf-8")
    if path.suffix in (".yaml", ".yml"):
        media_type = "application/yaml"
    elif path.suffix == ".json":
        media_type = "application/json"
    else:
        media_type = "text/markdown"
    return content, media_type


def read_task_file(session_id: str, relative_path: str) -> str:
    tasks_dir = (session_output_dir(session_id) / "tasks").resolve()
    full = (tasks_dir / relative_path).resolve()
    if not str(full).startswith(str(tasks_dir)):
        raise ValueError("Invalid task path")
    if not full.is_file():
        raise FileNotFoundError(f"Task not found: {relative_path}")
    return full.read_text(encoding="utf-8")


def build_zip(session_id: str) -> bytes:
    output_dir = session_output_dir(session_id)
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in output_dir.rglob("*"):
            if file.is_file():
                zf.write(file, arcname=file.relative_to(output_dir.parent))
    buf.seek(0)
    return buf.read()
