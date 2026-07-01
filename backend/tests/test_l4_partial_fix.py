"""Tests for L4 runtime guards and per-session LLM kwargs."""

from __future__ import annotations

from app.agent.agents.base import BaseAgent
from app.agent.l4_guards import apply_l4_runtime_guards, is_small_llm_model
from app.agent.state import initial_state


def test_is_small_llm_model():
    assert is_small_llm_model("gemma3:4b")
    assert is_small_llm_model("gemma3:1b")
    assert not is_small_llm_model("qwen2.5:7b")


def test_l4_bumps_tokens_and_timeout():
    rules, warnings = apply_l4_runtime_guards(
        {"spec_level": "L4", "ollama": {"max_tokens": 2048, "timeout_sec": 120}},
        global_llm_max_tokens=2048,
        active_llm_model="gemma3:4b",
    )
    assert rules["ollama"]["max_tokens"] == 8192
    assert rules["ollama"]["timeout_sec"] == 300
    assert rules["l4"]["tasks_per_batch"] == 12
    assert any("LLM_MAX_TOKENS" in w for w in warnings)
    assert any("small model" in w for w in warnings)


def test_l4_no_change_for_l2():
    rules, warnings = apply_l4_runtime_guards({"spec_level": "L2", "ollama": {}})
    assert warnings == []
    assert "l4" not in rules or rules.get("l4", {}).get("tasks_per_batch", 25) == 25


def test_llm_kwargs_from_rules():
    agent = BaseAgent(llm=object())
    state = initial_state(
        "s1",
        "idea",
        {
            "spec_level": "L4",
            "ollama": {"max_tokens": 8192, "temperature": 0.1, "timeout_sec": 300},
        },
        None,
    )
    kwargs = agent._llm_kwargs(state)
    assert kwargs["max_tokens"] == 8192
    assert kwargs["temperature"] == 0.1
    assert kwargs["timeout_sec"] == 300


def test_write_gaps_includes_l4_criteria(tmp_path, monkeypatch):
    from app.services import export as export_mod
    from app.services.export import write_gaps

    monkeypatch.setattr(export_mod, "OUTPUT_ROOT", tmp_path)

    path = write_gaps(
        "sess-1",
        {
            "status": "degraded",
            "reason": "l4_criteria_unmet:tasks_coverage",
            "failed_steps": [],
            "open_questions": [],
            "manual_actions": ["fix tasks"],
            "l4_criteria": {
                "artifacts_complete": True,
                "tasks_coverage": False,
                "reviewer_approved": False,
            },
            "unmet_l4_criteria": ["tasks_coverage", "reviewer_approved"],
        },
    )
    text = path.read_text(encoding="utf-8")
    assert "Unmet L4 Criteria" in text
    assert "tasks coverage" in text
    assert "tasks_coverage" in text
