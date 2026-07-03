"""Start or restart the agent graph for a session (agent-worker only)."""

from __future__ import annotations

import asyncio
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class SessionLaunchError(RuntimeError):
    """Raised when graph cannot be started."""


async def launch_session_graph(
    session_id: str,
    *,
    idea: str,
    rules_dict: dict[str, Any],
    monitoring_cfg: dict[str, Any],
) -> None:
    from app.config import get_settings
    from app.llm.provider_resolver import build_embedding_for_rules, build_llm_for_rules
    from app.services import provider_bootstrap
    from app.services.session_runner import session_runner
    from app.services.system_monitor import system_monitor

    app_settings = get_settings()
    llm_provider_name = rules_dict.get("llm_provider", app_settings.llm_provider)

    if llm_provider_name == "yandexgpt":
        if not app_settings.yandex_credentials_configured():
            raise SessionLaunchError(
                "YandexGPT не настроен. Задай YANDEX_FOLDER_ID и YANDEX_API_KEY в .env"
            )
    elif not await provider_bootstrap.ensure_providers(app_settings):
        raise SessionLaunchError(
            "Ollama недоступен. Запусти Ollama (и ollama-proxy), затем перезапусти agent-worker."
        )

    try:
        session_llm = build_llm_for_rules(rules_dict, app_settings)
        session_emb = build_embedding_for_rules(rules_dict, app_settings)
    except RuntimeError as e:
        raise SessionLaunchError(str(e)) from e

    if llm_provider_name == "ollama" and provider_bootstrap.is_stub_provider(session_llm):
        raise SessionLaunchError("LLM provider in stub mode — Ollama not connected")

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
        raise SessionLaunchError(str(e)) from e
