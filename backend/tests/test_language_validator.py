"""Tests for language_validator service."""

from __future__ import annotations

from app.services.language_validator import (
    output_language_instruction,
    should_validate_language,
    strip_exempt_segments,
    validate_artifact_language,
    validate_artifacts_language,
    validate_text_language,
)

RUSSIAN_PROSE = (
    "Цель проекта — создать сервис знакомств в Telegram. "
    "Пользователи заполняют анкету, получают подборку кандидатов "
    "и при взаимном интересе видят username собеседника. "
    "Архитектура включает FastAPI backend, PostgreSQL и Redis. "
    "Статус сессии: running. Endpoint: GET /api/v1/matches."
) * 2

ENGLISH_PROSE = (
    "The project goal is to build a Telegram dating service. "
    "Users fill a profile, receive candidate suggestions, "
    "and see the other party username on mutual interest. "
    "Architecture uses FastAPI backend, PostgreSQL and Redis. "
    "Session status: running. Endpoint: GET /api/v1/matches."
) * 2

INTAKE_BLOCK = """
[User clarifications]
- Q: What is the target audience?
  A: Young professionals in large cities
- Q: Какой бюджет?
  A: low
"""


def test_strip_exempts_tech_status_and_intake():
    cleaned = strip_exempt_segments(RUSSIAN_PROSE + INTAKE_BLOCK)
    lower = cleaned.lower()
    assert "fastapi" not in lower
    assert "postgresql" not in lower
    assert "running" not in lower
    assert "get" not in lower.split()
    assert "цель" in lower or "проекта" in lower


def test_validate_russian_passes():
    result = validate_text_language(RUSSIAN_PROSE, "ru")
    assert result.passed
    assert result.cyrillic_ratio >= 0.55


def test_validate_russian_fails_on_english():
    result = validate_text_language(ENGLISH_PROSE, "ru")
    assert not result.passed


def test_validate_english_passes():
    result = validate_text_language(ENGLISH_PROSE, "en")
    assert result.passed


def test_validate_english_fails_on_russian():
    result = validate_text_language(RUSSIAN_PROSE, "en")
    assert not result.passed


def test_short_text_skips_strict_check():
    result = validate_text_language("FastAPI only", "ru")
    assert result.passed


def test_validate_artifacts_language_returns_issues():
    issues = validate_artifacts_language(
        {"product_spec": ENGLISH_PROSE, "api_spec": RUSSIAN_PROSE},
        "ru",
    )
    keys = {i["location"] for i in issues}
    assert "product_spec#language" in keys
    assert "api_spec#language" not in keys


def test_validate_artifact_language_prefixes_key():
    result = validate_artifact_language(ENGLISH_PROSE, "arch_spec", "ru")
    assert not result.passed
    assert all(v.startswith("arch_spec:") for v in result.violations)


def test_should_validate_language_respects_flag():
    assert should_validate_language({"output": {"language": "ru"}})
    assert not should_validate_language({"output": {"language": "ru", "validate_language": False}})


def test_output_language_instruction_mentions_exemptions():
    text = output_language_instruction({"output": {"language": "ru"}})
    assert "Russian" in text
    assert "FastAPI" in text
    assert "statuses" in text.lower() or "status" in text.lower()


def test_validate_intake_questions_russian():
    from app.services.language_validator import validate_intake_questions

    english = [
        {"text": "What is the target audience for this product?", "options": ["Web", "Mobile"]}
    ]
    russian = [
        {"text": "Кто является целевой аудиторией этого продукта?", "options": ["Web", "Mobile"]}
    ]
    assert validate_intake_questions(english, "ru")
    assert not validate_intake_questions(russian, "ru")
