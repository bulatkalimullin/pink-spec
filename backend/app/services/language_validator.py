"""Validate artifact/UI text language with exemptions for technical tokens."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Session / task statuses — never translated
STATUS_TOKENS = frozenset(
    {
        "running",
        "completed",
        "completed_partial",
        "failed",
        "degraded",
        "pending",
        "todo",
        "paused",
        "stuck",
        "waiting_user",
        "cancelled",
        "connected",
        "connecting",
        "reconnecting",
        "disconnected",
        "error",
        "high",
        "medium",
        "low",
        "critical",
    }
)

# Common technology tokens — kept in Latin regardless of output language
TECH_TOKENS = frozenset(
    {
        "fastapi",
        "postgresql",
        "postgres",
        "redis",
        "aiogram",
        "react",
        "typescript",
        "javascript",
        "python",
        "docker",
        "kubernetes",
        "jwt",
        "oauth",
        "oauth2",
        "tls",
        "ssl",
        "https",
        "http",
        "api",
        "rest",
        "graphql",
        "websocket",
        "json",
        "yaml",
        "markdown",
        "uuid",
        "telegram",
        "webapp",
        "chromadb",
        "langgraph",
        "ollama",
        "prometheus",
        "grafana",
        "nginx",
        "s3",
        "minio",
        "celery",
        "github",
        "npm",
        "pytest",
        "haversine",
        "jaccard",
        "aes",
        "hmac",
        "sha256",
        "bcrypt",
        "gdpr",
        "initdata",
        "middleware",
        "endpoint",
        "enum",
        "boolean",
        "integer",
        "float",
        "string",
        "timestamp",
        "bigint",
        "varchar",
    }
)

HTTP_METHODS = frozenset({"GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"})

SUPPORTED_LANGUAGES: dict[str, dict[str, str]] = {
    "en": {"label": "English", "native": "English"},
    "ru": {"label": "Russian", "native": "Русский"},
}

_EXEMPT_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"```[\s\S]*?```"),
    re.compile(r"`[^`\n]+`"),
    re.compile(r"https?://\S+"),
    re.compile(r"/[a-zA-Z0-9_{}/.\-:*]+"),
    re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.I),
    re.compile(r"\b(?:Q|A):\s*.+$", re.M),
    re.compile(r"^\s*[-*]\s*Q:\s*.+$", re.M),
    re.compile(r"\*\*Artifact Key:\*\*\s*\S+", re.I),
    re.compile(r"Artifact Key:\s*[a-z][a-z0-9_]+", re.I),
    re.compile(r"\{[^{}]+\}"),
    re.compile(r"\[[^\]]+\]\([^)]+\)"),
]

_WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9_'-]*")


@dataclass
class LanguageValidationResult:
    language: str
    passed: bool
    cyrillic_ratio: float = 0.0
    latin_ratio: float = 0.0
    sampled_words: int = 0
    violations: list[str] = field(default_factory=list)


def output_language_instruction(rules: dict[str, Any]) -> str:
    """Prompt block for agents — prose language + exempt categories."""
    output = rules.get("output") or {}
    lang = str(output.get("language", "en")).lower()
    meta = SUPPORTED_LANGUAGES.get(lang, {"label": lang, "native": lang})
    label = meta["label"]
    return (
        f"OUTPUT LANGUAGE: {label} ({lang}). "
        f"Write ALL headings, descriptions, goals, and explanatory prose in {label}. "
        "DO NOT translate these (keep as-is): technology and product names "
        "(FastAPI, PostgreSQL, Redis, Telegram), API paths, HTTP methods, "
        "HTTP status codes, enum values, JSON field names, code blocks, "
        "artifact keys, UUIDs, session/task statuses, and intake Q/A prefixes."
    )


def strip_exempt_segments(text: str) -> str:
    """Remove segments that should not affect language detection."""
    cleaned = text
    for pattern in _EXEMPT_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)

    tokens: list[str] = []
    for match in _WORD_RE.finditer(cleaned):
        word = match.group(0)
        lower = word.lower()
        if lower in STATUS_TOKENS or lower in TECH_TOKENS:
            continue
        if word in HTTP_METHODS:
            continue
        if word.isupper() and len(word) <= 6:
            continue
        if re.fullmatch(r"[A-Z][a-z]+(?:[A-Z][a-zA-Z0-9]*)+", word):
            continue
        if "_" in word and word.isascii():
            continue
        tokens.append(word)

    return " ".join(tokens)


def _script_ratios(text: str) -> tuple[float, float, int]:
    cyr = lat = 0
    for ch in text:
        if "\u0400" <= ch <= "\u04FF":
            cyr += 1
        elif ch.isascii() and ch.isalpha():
            lat += 1
    total = cyr + lat
    if total == 0:
        return 0.0, 0.0, 0
    return cyr / total, lat / total, total


def validate_text_language(text: str, expected_language: str) -> LanguageValidationResult:
    """Heuristic language check after stripping exempt technical tokens."""
    lang = expected_language.lower()
    if lang not in SUPPORTED_LANGUAGES:
        return LanguageValidationResult(
            language=lang,
            passed=True,
            violations=[f"Unsupported language {lang!r} — skipped validation"],
        )

    prose = strip_exempt_segments(text)
    cyr_ratio, lat_ratio, sampled = _script_ratios(prose)
    result = LanguageValidationResult(
        language=lang,
        passed=True,
        cyrillic_ratio=cyr_ratio,
        latin_ratio=lat_ratio,
        sampled_words=sampled,
    )

    if sampled < 20:
        return result

    if lang == "ru":
        if cyr_ratio < 0.55:
            result.passed = False
            result.violations.append(
                f"Expected Russian prose but only {cyr_ratio:.0%} Cyrillic "
                f"after exempting technical tokens (need ≥55%)"
            )
        if lat_ratio > 0.45 and cyr_ratio < 0.65:
            result.violations.append(
                f"High Latin ratio ({lat_ratio:.0%}) suggests English prose mixed in"
            )
    elif lang == "en":
        if cyr_ratio > 0.08:
            result.passed = False
            result.violations.append(
                f"Expected English prose but {cyr_ratio:.0%} Cyrillic found "
                f"(max 8% allowed)"
            )
        if lat_ratio < 0.75:
            result.passed = False
            result.violations.append(
                f"Low Latin ratio ({lat_ratio:.0%}) — prose may not be English"
            )

    if result.violations and result.passed:
        result.passed = False

    return result


def validate_artifact_language(
    content: str,
    artifact_key: str,
    expected_language: str,
) -> LanguageValidationResult:
    result = validate_text_language(content, expected_language)
    if not result.passed:
        result.violations = [
            f"{artifact_key}: {v}" for v in result.violations
        ]
    return result


def validate_artifacts_language(
    artifacts: dict[str, str],
    expected_language: str,
    *,
    min_chars: int = 200,
) -> list[dict[str, Any]]:
    """Validate multiple artifacts; return reviewer-style issue dicts."""
    issues: list[dict[str, Any]] = []
    for key, body in artifacts.items():
        if not body or len(body.strip()) < min_chars:
            continue
        result = validate_artifact_language(body, key, expected_language)
        if not result.passed:
            for violation in result.violations:
                issues.append(
                    {
                        "severity": "medium",
                        "description": f"Language compliance: {violation}",
                        "location": f"{key}#language",
                    }
                )
    return issues


def validate_intake_questions(
    questions: list[dict[str, Any]],
    expected_language: str,
) -> list[str]:
    """Validate intake question text (not JSON keys or short option tokens)."""
    violations: list[str] = []
    for q in questions:
        text = str(q.get("text", "")).strip()
        if len(text) >= 12:
            result = validate_text_language(text, expected_language)
            if not result.passed:
                violations.extend(f"question: {v}" for v in result.violations)
        for opt in q.get("options") or []:
            opt_text = str(opt).strip()
            if len(opt_text) >= 20:
                opt_result = validate_text_language(opt_text, expected_language)
                if not opt_result.passed:
                    violations.extend(f"option: {v}" for v in opt_result.violations)
    return violations


def should_validate_language(rules: dict[str, Any]) -> bool:
    output = rules.get("output") or {}
    if output.get("validate_language") is False:
        return False
    return bool(output.get("language"))
