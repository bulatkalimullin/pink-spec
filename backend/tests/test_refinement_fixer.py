"""Tests for batch refinement fixer agent."""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.agents.refinement_fixer import RefinementFixerAgent
from app.services import export as export_mod
from app.services.export import write_artifact


@pytest.fixture
def output_root(tmp_path, monkeypatch):
    monkeypatch.setattr(export_mod, "OUTPUT_ROOT", tmp_path)
    return tmp_path


@pytest.mark.asyncio
async def test_refinement_fixer_patches_all_artifacts_in_one_run(output_root):
    session_id = "fixer-session"
    write_artifact(session_id, "product_spec", "# Product\n\nOld scope")
    write_artifact(session_id, "api_spec", "# API\n\nOld endpoints")

    llm = MagicMock()
    llm.generate = AsyncMock(
        side_effect=[
            "<<<<<<< SEARCH\nOld scope\n=======\nNew scope\n>>>>>>> REPLACE",
            "<<<<<<< SEARCH\nOld endpoints\n=======\nNew endpoints\n>>>>>>> REPLACE",
        ]
    )
    agent = RefinementFixerAgent(llm=llm)

    state = {
        "session_id": session_id,
        "idea": "test",
        "started_at": time.time(),
        "spec_level": "L4",
        "rules": {"artifacts": {"mode": "patch"}, "ollama": {}},
        "refinement_issues": {
            "product_spec": [
                {"severity": "high", "description": "fix scope", "location": "product_spec#scope"},
                {"severity": "medium", "description": "add metrics", "location": "product_spec#metrics"},
            ],
            "api_spec": [
                {"severity": "high", "description": "fix endpoints", "location": "api_spec#paths"},
            ],
        },
        "agent_outputs": {"reviewer": "{}"},
        "artifacts": {"product_spec": "<x>", "api_spec": "<y>"},
        "patch_unchanged_counts": {},
        "pipeline": [{"id": "reviewer", "executor": "builtin:reviewer"}],
    }

    result = await agent.run(state)

    assert llm.generate.call_count == 2
    assert result["refinement_pending"] is False
    assert "refinement_fixer" in result["agent_outputs"]
    assert "reviewer" not in result["agent_outputs"]
    assert "New scope" in (output_root / session_id / "docs" / "product_spec.md").read_text()
    assert "New endpoints" in (output_root / session_id / "docs" / "api_spec.openapi.yaml").read_text()
