"""Researcher agent — RAG retrieval and context enrichment."""

from __future__ import annotations

from typing import Any

from app.agent.agents.base import BaseAgent
from app.agent.stage_progress import emit_stage_changed
from app.agent.state import MultiAgentState
from app.services.log_bus import log_bus


class ResearcherAgent(BaseAgent):
    agent_id = "researcher"

    def __init__(self, llm, embedding_provider, rag_cfg: dict) -> None:
        super().__init__(llm)
        self._embedding_provider = embedding_provider
        self._rag_cfg = rag_cfg

    async def _execute(self, state: MultiAgentState) -> dict[str, Any]:
        session_id = state["session_id"]
        rules = state["rules"]
        rag_cfg = rules.get("rag", {})

        if not rag_cfg.get("enabled", False):
            await self._log(session_id, "info", "RAG disabled — skipping researcher phase")
            saturation_report = {
                "status": "skipped",
                "iterations": 0,
                "chunks_collected": 0,
                "context_brief": "",
            }
            return {
                **state,
                "agent_outputs": {**state.get("agent_outputs", {}), "researcher": "skipped"},
                "saturation_report": saturation_report,
                "current_agent": "supervisor",
            }

        from app.rag.ingest import ingest_sources
        from app.rag.retriever import BM25Retriever, ChromaRetriever
        from app.rag.saturation import run_saturation

        retriever, retriever_kind = await self._build_retriever(session_id)

        sources = rag_cfg.get("sources", [])
        if sources:
            await emit_stage_changed(
                state,
                stage_id="ingest",
                label="Загружаем источники",
                detail=f"{len(sources)} источник(ов)",
                agent_id="researcher",
                sub_progress=0.2,
            )
            await self._log(session_id, "info", f"Ingesting {len(sources)} source(s)...")
            ingest_result = await ingest_sources(sources, retriever, session_id)
            await self._log(
                session_id,
                "info",
                f"Ingest complete: {ingest_result['files_ok']} files, {ingest_result['chunks']} chunks",
            )

        idea = state["idea"]
        seed_queries = [
            idea,
            f"{rules.get('project', {}).get('domain', '')} best practices",
            f"{rules.get('project', {}).get('name', '')} architecture patterns",
        ]
        sat_cfg = {**rag_cfg.get("saturation", {}), "top_k": rag_cfg.get("top_k", 8)}

        saturation_report = await self._run_saturation_with_fallback(
            state=state,
            session_id=session_id,
            retriever=retriever,
            retriever_kind=retriever_kind,
            sources=sources,
            seed_queries=seed_queries,
            sat_cfg=sat_cfg,
        )

        await self._log(
            session_id,
            "info",
            f"Saturation {saturation_report['status']}: {saturation_report['chunks_collected']} chunks in {saturation_report['iterations']} iterations",
        )

        await emit_stage_changed(
            state,
            stage_id="context_ready",
            label="Контекст получен",
            detail=f"{saturation_report['chunks_collected']} фрагментов",
            agent_id="researcher",
            sub_progress=1.0,
        )

        new_context = dict(state.get("context", {}))
        new_context["saturation_report"] = saturation_report

        return {
            **state,
            "agent_outputs": {
                **state.get("agent_outputs", {}),
                "researcher": saturation_report["status"],
            },
            "saturation_report": saturation_report,
            "context": new_context,
            "current_agent": "supervisor",
        }

    async def _build_retriever(self, session_id: str) -> tuple[Any, str]:
        from app.rag.retriever import BM25Retriever, ChromaRetriever

        try:
            return (
                ChromaRetriever(
                    session_id=session_id, embedding_provider=self._embedding_provider
                ),
                "chroma",
            )
        except Exception as e:
            await self._log(session_id, "warn", f"ChromaDB unavailable ({e}), using BM25 fallback")
            await log_bus.emit(
                session_id,
                "fallback_triggered",
                {
                    "layer": "rag",
                    "step": "retriever",
                    "from": "chroma",
                    "to": "bm25",
                    "message": f"ChromaDB unavailable: {e}",
                },
            )
            return BM25Retriever(), "bm25"

    async def _run_saturation_with_fallback(
        self,
        *,
        state: MultiAgentState,
        session_id: str,
        retriever: Any,
        retriever_kind: str,
        sources: list[str],
        seed_queries: list[str],
        sat_cfg: dict,
    ) -> dict[str, Any]:
        from app.rag.ingest import ingest_sources
        from app.rag.retriever import BM25Retriever
        from app.rag.saturation import run_saturation

        try:
            return await run_saturation(
                session_id=session_id,
                seed_queries=seed_queries,
                embedding_provider=self._embedding_provider,
                retriever=retriever,
                cfg=sat_cfg,
                state=state,
            )
        except Exception as e:
            await self._log(
                session_id,
                "warn",
                f"RAG saturation failed ({e}), trying BM25 fallback",
            )

        if retriever_kind == "chroma":
            await log_bus.emit(
                session_id,
                "fallback_triggered",
                {
                    "layer": "rag",
                    "step": "saturation",
                    "from": "chroma",
                    "to": "bm25",
                    "message": "Embedding saturation failed; retrying with BM25 retriever",
                },
            )
            bm25 = BM25Retriever()
            if sources:
                await ingest_sources(sources, bm25, session_id)
            retriever = bm25
        else:
            await log_bus.emit(
                session_id,
                "fallback_triggered",
                {
                    "layer": "rag",
                    "step": "saturation",
                    "from": "bm25",
                    "to": "bm25_novelty_skip",
                    "message": "BM25 saturation failed; retrying without embedding novelty",
                },
            )

        try:
            return await run_saturation(
                session_id=session_id,
                seed_queries=seed_queries,
                embedding_provider=self._embedding_provider,
                retriever=retriever,
                cfg={**sat_cfg, "skip_embedding_novelty": True},
                state=state,
            )
        except Exception as e:
            await self._log(
                session_id,
                "warn",
                f"RAG saturation fallback failed ({e}), skipping researcher phase",
            )
            await log_bus.emit(
                session_id,
                "fallback_triggered",
                {
                    "layer": "rag",
                    "step": "saturation",
                    "from": retriever_kind,
                    "to": "skipped",
                    "message": str(e),
                },
            )
            return {
                "status": "skipped",
                "iterations": 0,
                "chunks_collected": 0,
                "context_brief": "",
                "query_history": seed_queries,
            }
