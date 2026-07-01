"""Tests for intake agent parsing and answer merging."""

from __future__ import annotations

from app.agent.agents.intake_agent import _parse_intake_result
from app.agent.state import initial_state
from app.services.intake import merge_answers_into_state


def test_parse_intake_ready():
    raw = '{"ready": true, "summary": "Enough context", "questions": []}'
    result = _parse_intake_result(raw, max_questions=8)
    assert result["ready"] is True
    assert result["questions"] == []


def test_parse_intake_questions_forces_not_ready():
    raw = """{
        "ready": true,
        "summary": "missing platform",
        "questions": [
            {"text": "Target platform?", "priority": "critical", "options": ["Web", "Mobile"]},
            {"text": "Auth model?", "priority": "high", "options": []}
        ]
    }"""
    result = _parse_intake_result(raw, max_questions=8)
    assert result["ready"] is False
    assert len(result["questions"]) == 2
    assert result["questions"][0]["text"] == "Target platform?"
    assert result["questions"][0]["options"] == ["Web", "Mobile"]


def test_parse_intake_respects_max_questions():
    import json

    questions = [{"text": f"Q{i}?", "priority": "high"} for i in range(10)]
    raw = json.dumps({"ready": False, "questions": questions})
    result = _parse_intake_result(raw, max_questions=3)
    assert len(result["questions"]) == 3


def test_merge_answers_into_idea():
    state = initial_state("sess-1", "Build a todo app", {"spec_level": "L2"}, 900)
    qa = [
        {"id": "q1", "text": "Target users?", "answer": "Students"},
        {"id": "q2", "text": "Platform?", "answer": "Web"},
    ]
    merged = merge_answers_into_state(state, qa)
    assert "Students" in merged["idea"]
    assert "Target users?" in merged["idea"]
    assert merged["intake_complete"] is True
    assert merged["intake_answers"]["q1"] == "Students"
