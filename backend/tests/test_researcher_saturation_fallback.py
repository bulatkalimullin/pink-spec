"""Tests for researcher RAG saturation fallback."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agent.agents.researcher import ResearcherAgent
from app.agent.state import initial_state


@pytest.mark.asyncio
async def test_saturation_falls_back_to_bm25_after_embed_failure():
    llm = MagicMock()
    embedding = MagicMock()
    agent = ResearcherAgent(llm, embedding, {})

    state = initial_state(
        session_id="sess-1",
        idea="test idea",
        rules={
            "spec_level": "L1",
            "rag": {
                "enabled": True,
                "sources": [],
                "saturation": {"max_iterations": 2, "min_chunks": 1},
            },
            "project": {"domain": "general", "name": "demo"},
        },
        time_budget_sec=300,
    )

    chroma = MagicMock()
    bm25 = MagicMock()
    saturation_reports = [
        RuntimeError("Ollama embed failed"),
        {
            "status": "partial",
            "iterations": 1,
            "chunks_collected": 2,
            "context_brief": "ctx",
            "query_history": ["q"],
        },
    ]

    with (
        patch.object(agent, "_build_retriever", AsyncMock(return_value=(chroma, "chroma"))),
        patch(
            "app.rag.saturation.run_saturation",
            AsyncMock(side_effect=saturation_reports),
        ) as run_saturation,
        patch("app.rag.retriever.BM25Retriever", return_value=bm25),
        patch("app.agent.agents.researcher.log_bus.emit", AsyncMock()) as emit,
    ):
        result = await agent._execute(state)

    assert run_saturation.await_count == 2
    second_call = run_saturation.await_args_list[1]
    assert second_call.kwargs["retriever"] is bm25
    assert second_call.kwargs["cfg"]["skip_embedding_novelty"] is True
    assert result["saturation_report"]["chunks_collected"] == 2
    assert any(
        call.args[1] == "fallback_triggered" and call.args[2]["to"] == "bm25"
        for call in emit.call_args_list
    )
