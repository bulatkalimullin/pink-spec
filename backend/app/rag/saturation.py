"""Embedding Saturation algorithm — iterative retrieval until novelty drops below threshold."""

from __future__ import annotations

import math
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


def _cosine_distance(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return 1.0 - dot / (norm_a * norm_b)


def _min_distance_to_set(vec: list[float], collected: list[list[float]]) -> float:
    if not collected:
        return 1.0
    return min(_cosine_distance(vec, c) for c in collected)


async def run_saturation(
    session_id: str,
    seed_queries: list[str],
    embedding_provider,
    retriever,
    cfg: dict,
    state: Any | None = None,
) -> dict[str, Any]:
    """
    Returns saturation_report:
      {status, iterations, chunks_collected, context_brief, query_history}
    """
    from app.services.log_bus import log_bus

    if state is not None:
        from app.agent.stage_progress import emit_stage_changed

        await emit_stage_changed(
            state,
            stage_id="saturation",
            label="Собираем контекст",
            detail="Подготовка…",
            agent_id="researcher",
            sub_progress=0.0,
        )

    max_iter: int = cfg.get("max_iterations", 5)
    top_k: int = cfg.get("top_k", 8)
    novelty_threshold: float = cfg.get("novelty_threshold", 0.15)
    min_chunks: int = cfg.get("min_chunks", 10)
    query_expansion: bool = cfg.get("query_expansion", True)

    collected_vecs: list[list[float]] = []
    collected_texts: list[str] = []
    queries = list(seed_queries)
    query_history: list[str] = list(seed_queries)

    for iteration in range(1, max_iter + 1):
        # Retrieve
        retrieved: list[dict] = []
        for q in queries:
            chunks = await retriever.retrieve(q, top_k=top_k)
            retrieved.extend(chunks)

        # Deduplicate by content
        seen = set(collected_texts)
        new_chunks = [c for c in retrieved if c["text"] not in seen]

        if not new_chunks:
            avg_novelty = 0.0
        elif cfg.get("skip_embedding_novelty"):
            for chunk in new_chunks:
                collected_texts.append(chunk["text"])
            avg_novelty = 1.0
        else:
            vecs = await embedding_provider.embed_documents([c["text"] for c in new_chunks])
            novelties = [_min_distance_to_set(v, collected_vecs) for v in vecs]
            avg_novelty = sum(novelties) / len(novelties)

            for chunk, vec, novelty in zip(new_chunks, vecs, novelties, strict=True):
                if novelty >= novelty_threshold:
                    collected_texts.append(chunk["text"])
                    collected_vecs.append(vec)

        await log_bus.emit(
            session_id,
            "saturation_progress",
            {
                "iteration": iteration,
                "chunks": len(collected_texts),
                "novelty": round(avg_novelty, 4),
                "queries_this_round": len(queries),
            },
        )

        if state is not None:
            from app.agent.stage_progress import emit_stage_changed

            sub = iteration / max(max_iter, 1)
            await emit_stage_changed(
                state,
                stage_id="saturation",
                label="Собираем контекст",
                detail=f"Итерация {iteration}/{max_iter} · {len(collected_texts)} фрагментов",
                agent_id="researcher",
                sub_progress=sub,
                saturation_iteration=iteration,
                saturation_max=max_iter,
            )

        satisfied = avg_novelty < novelty_threshold and len(collected_texts) >= min_chunks
        if satisfied or iteration == max_iter:
            break

        # Expand queries via LLM if enabled
        if query_expansion:
            queries = await _expand_queries(queries, collected_texts[-5:], session_id=session_id)
            query_history.extend(queries)

    context_brief = _build_context_brief(collected_texts)
    status = "complete" if len(collected_texts) >= min_chunks else "partial"

    return {
        "status": status,
        "iterations": iteration,
        "chunks_collected": len(collected_texts),
        "context_brief": context_brief,
        "query_history": query_history,
    }


async def _expand_queries(
    current_queries: list[str], sample_chunks: list[str], session_id: str
) -> list[str]:
    """Use a simple heuristic expansion (LLM call is optional and skipped if no provider)."""
    # In full implementation this would call the LLM for query expansion.
    # Here we produce suffix variants of existing queries as a lightweight fallback.
    expansions = []
    for q in current_queries[:3]:
        expansions.append(q + " implementation details")
        expansions.append(q + " best practices")
    return expansions[:4]


def _build_context_brief(texts: list[str], max_chars: int = 6000) -> str:
    brief = "\n\n---\n\n".join(texts)
    if len(brief) > max_chars:
        brief = brief[:max_chars] + "\n\n[truncated]"
    return brief
