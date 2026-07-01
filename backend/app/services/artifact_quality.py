"""Artifact quality gates: key validation, duplicate detection, assumption extraction."""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

_ASSUMPTION_RE = re.compile(r"\[ASSUMPTION:\s*([^\]]+)\]", re.IGNORECASE)
_ARTIFACT_KEY_RE = re.compile(
    r"^\s*\*?\*?Artifact Key:\*?\*?\s*([a-z][a-z0-9_]+)",
    re.IGNORECASE | re.MULTILINE,
)


class ArtifactQualityError(ValueError):
    """Raised when generated artifact fails quality gates."""


def extract_assumptions(content: str) -> list[str]:
    """Parse [ASSUMPTION: ...] markers from artifact text."""
    return [m.strip() for m in _ASSUMPTION_RE.findall(content) if m.strip()]


def validate_artifact_key(content: str, expected_key: str) -> tuple[bool, str]:
    """
    Ensure generated content declares the correct Artifact Key.
    Returns (ok, message).
    """
    if not content or len(content.strip()) < 50:
        return False, "Artifact content too short or empty"
    match = _ARTIFACT_KEY_RE.search(content)
    if not match:
        return False, f"Missing 'Artifact Key: {expected_key}' header"
    found = match.group(1).strip().lower()
    if found != expected_key.lower():
        return False, f"Wrong artifact key: expected {expected_key!r}, got {found!r}"
    return True, ""


def content_similarity(a: str, b: str) -> float:
    """Normalized similarity ratio between two texts."""
    if not a or not b:
        return 0.0
    a_norm = _normalize_for_compare(a[:8000])
    b_norm = _normalize_for_compare(b[:8000])
    return SequenceMatcher(None, a_norm, b_norm).ratio()


def _normalize_for_compare(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def find_duplicate_artifact(
    content: str,
    existing: dict[str, str],
    *,
    threshold: float = 0.85,
    exclude_key: str | None = None,
) -> tuple[str, float] | None:
    """If content is too similar to another artifact, return (other_key, similarity)."""
    for key, other in existing.items():
        if exclude_key and key == exclude_key:
            continue
        if not other or len(other.strip()) < 100:
            continue
        sim = content_similarity(content, other)
        if sim >= threshold:
            return key, sim
    return None


def load_existing_artifact_texts(session_id: str, exclude_key: str | None = None) -> dict[str, str]:
    """Load on-disk artifact bodies for duplicate comparison."""
    from app.services.artifact_store import load_manifest_file, read_artifact

    manifest = load_manifest_file(session_id)
    artifacts = manifest.get("artifacts") or {}
    out: dict[str, str] = {}
    for key in artifacts:
        if exclude_key and key == exclude_key:
            continue
        try:
            body, _ = read_artifact(session_id, key, manifest)
            out[key] = body
        except FileNotFoundError:
            continue
    return out


def validate_artifact_for_save(
    session_id: str,
    artifact_key: str,
    content: str,
    *,
    check_duplicates: bool = True,
    require_key: bool = True,
) -> tuple[str, list[str]]:
    """
    Run quality gates. Returns (content, assumptions).
    Raises ArtifactQualityError on failure.
    """
    if require_key:
        ok, msg = validate_artifact_key(content, artifact_key)
        if not ok:
            raise ArtifactQualityError(msg)
    elif not content or len(content.strip()) < 50:
        raise ArtifactQualityError("Artifact content too short or empty")

    if check_duplicates:
        existing = load_existing_artifact_texts(session_id, exclude_key=artifact_key)
        dup = find_duplicate_artifact(content, existing, exclude_key=artifact_key)
        if dup:
            other_key, sim = dup
            raise ArtifactQualityError(
                f"Content duplicates artifact {other_key!r} (similarity {sim:.2f})"
            )

    return content, extract_assumptions(content)


def normalize_embedding_vector(vec: list) -> list[float]:
    """Convert numpy scalars / nested types to plain Python floats for ChromaDB."""
    out: list[float] = []
    for x in vec:
        if isinstance(x, (list, tuple)):
            out.extend(float(v) for v in x)
        else:
            out.append(float(x))
    return out


def normalize_embedding_rows(vecs: list[list]) -> list[list[float]]:
    return [normalize_embedding_vector(row) for row in vecs]


def deduplicate_tasks(tasks: list[dict]) -> list[dict]:
    """Merge tasks with identical normalized titles; renumber ids sequentially."""
    seen: dict[str, dict] = {}
    order: list[str] = []
    for task in tasks:
        title_key = re.sub(r"\s+", " ", task.get("title", "").lower().strip())
        if not title_key:
            continue
        if title_key in seen:
            existing = seen[title_key]
            for field in ("spec_refs", "depends_on", "steps", "notes"):
                if isinstance(task.get(field), list):
                    merged = list(existing.get(field) or [])
                    for item in task[field]:
                        if item not in merged:
                            merged.append(item)
                    existing[field] = merged
            continue
        seen[title_key] = dict(task)
        order.append(title_key)

    deduped = [seen[k] for k in order]
    for i, task in enumerate(deduped, start=1):
        task["id"] = f"{i:03d}"
    return deduped


def resolve_spec_refs(tasks: list[dict], session_id: str) -> list[dict]:
    """Drop spec_refs pointing to non-existent files."""
    from app.services.export import session_output_dir

    docs = session_output_dir(session_id) / "docs"
    if not docs.is_dir():
        return tasks
    existing = {f"docs/{p.name}" for p in docs.iterdir() if p.is_file()}
    existing.add("docs/SPEC_CANON.md")
    cleaned = []
    for task in tasks:
        t = dict(task)
        refs = [r for r in (t.get("spec_refs") or []) if r in existing]
        t["spec_refs"] = refs
        cleaned.append(t)
    return cleaned


def stack_constraint_prompt(rules: dict) -> str:
    """Build task decomposer constraint line from rules.constraints.stack."""
    stack = (rules.get("constraints") or {}).get("stack") or {}
    backend = stack.get("backend") or []
    frontend = stack.get("frontend") or []
    forbidden = stack.get("forbidden") or []
    lines = []
    if backend:
        lines.append(f"Backend stack ONLY: {', '.join(backend)}")
    if frontend:
        lines.append(f"Frontend stack ONLY: {', '.join(frontend)}")
    if forbidden:
        lines.append(f"Do NOT generate tasks for: {', '.join(forbidden)}")
    return "\n".join(lines)


def inject_nfr_from_intake(rules: dict, idea: str, answers: dict) -> dict:
    """Auto-populate empty NFR fields from intake answers and idea text."""
    import json

    rules = dict(rules)
    nfr = dict(rules.get("nfr") or {})
    combined = f"{idea} {json.dumps(answers, ensure_ascii=False)}".lower()

    if not nfr.get("latency_p95_ms") and ("rps" in combined or "3000" in combined):
        nfr["latency_p95_ms"] = 200
    if not nfr.get("availability"):
        nfr["availability"] = "99.5%"
    if not nfr.get("security") and any(
        k in combined for k in ("шифр", "encrypt", "hash", "хэш", "security")
    ):
        nfr["security"] = ["TLS 1.3", "AES-256 at rest", "Telegram initData HMAC"]

    rules["nfr"] = nfr
    return rules
