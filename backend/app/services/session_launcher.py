"""Start or restart the agent graph for a session."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from fastapi import HTTPException

logger = structlog.get_logger(__name__)


async def launch_session_graph(
    session_id: str,
    *,
    idea: str,
    rules_dict: dict[str, Any],
    monitoring_cfg: dict[str, Any],
) -> None:
    from app.main import ensure_providers, is_stub_provider, settings as app_settings
    from app.llm.provider_resolver import build_embedding_for_rules, build_llm_for_rules
    from app.services.session_runner import session_runner
    from app.services.system_monitor import system_monitor

    llm_provider_name = rules_dict.get("llm_provider", app_settings.llm_provider)

    if llm_provider_name == "yandexgpt":
        if not app_settings.yandex_credentials_configured():
            raise HTTPException(
                503,
                "YandexGPT не настроен. Задай YANDEX_FOLDER_ID и один из: "
                "YANDEX_API_KEY, YANDEX_PASSPORT_TOKEN в .env",
            )
    elif not await ensure_providers():
        raise HTTPException(
            503,
            "Ollama недоступен. Запусти Ollama (и ollama-proxy), затем перезапусти backend.",
        )

    try:
        session_llm = build_llm_for_rules(rules_dict, app_settings)
        session_emb = build_embedding_for_rules(rules_dict, app_settings)
    except RuntimeError as e:
        raise HTTPException(503, str(e)) from e

    if llm_provider_name == "ollama" and is_stub_provider(session_llm):
        raise HTTPException(503, "LLM provider in stub mode — Ollama not connected")

    async def _run(cancel_event: asyncio.Event):
        from app.agent.graph import run_graph

        system_monitor.add_session(session_id, monitoring_cfg)
        try:
            await run_graph(
                session_id=session_id,
                idea=idea,
                rules=rules_dict,
                llm_provider=session_llm,
                embedding_provider=session_emb,
                cancel_event=cancel_event,
            )
        finally:
            system_monitor.remove_session(session_id)

    try:
        await session_runner.start(session_id, _run)
    except RuntimeError as e:
        raise HTTPException(409, str(e)) from e
