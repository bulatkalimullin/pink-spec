"""Serve JSON Schema for the rules config (used by Monaco editor)."""

from __future__ import annotations

from fastapi import APIRouter

from app.schemas.rules import Rules
from app.services.language_validator import SUPPORTED_LANGUAGES
from app.services.ollama_presets import (
    EMBEDDING_FALLBACK_OPTIONS,
    OLLAMA_EMBEDDING_HINTS,
    OLLAMA_LLM_HINTS,
    enrich_presets,
)

router = APIRouter(prefix="/api/v1", tags=["schema"])

YANDEX_MODELS = [
    {"id": "yandexgpt-lite", "label": "YandexGPT Lite", "description": "Быстрая модель для черновиков"},
    {"id": "yandexgpt", "label": "YandexGPT Pro", "description": "Основная модель"},
    {"id": "yandexgpt-32k", "label": "YandexGPT 32k", "description": "Большой контекст"},
]


@router.get("/schema/rules")
async def get_rules_schema():
    return Rules.model_json_schema()


@router.get("/languages")
async def get_supported_languages():
    return {
        "languages": [
            {"code": code, **meta} for code, meta in SUPPORTED_LANGUAGES.items()
        ],
        "default": "en",
    }


@router.get("/llm-providers")
async def get_llm_providers():
    from app.config import get_settings
    from app.llm.ollama_provider import check_ollama

    settings = get_settings()
    ollama_models: list[str] = []
    ollama_reachable = False
    try:
        tags = await check_ollama(settings.ollama_base_url)
        ollama_reachable = True
        ollama_models = [m.get("name", "") for m in tags.get("models", []) if m.get("name")]
    except Exception:
        pass

    llm_hints = list(dict.fromkeys([*ollama_models, *OLLAMA_LLM_HINTS]))
    embedding_hints = list(dict.fromkeys([*OLLAMA_EMBEDDING_HINTS, *ollama_models]))
    presets = enrich_presets(ollama_models)

    return {
        "default": settings.llm_provider,
        "providers": [
            {
                "id": "ollama",
                "label": "Ollama (local)",
                "description": "Локальные модели через Ollama",
                "available": ollama_reachable,
                "models": llm_hints,
                "installed_models": ollama_models,
                "llm_model_hints": OLLAMA_LLM_HINTS,
                "embedding_model_hints": embedding_hints,
                "presets": presets,
                "embedding_fallback_options": EMBEDDING_FALLBACK_OPTIONS,
                "default_model": settings.ollama_llm_model,
                "default_config": {
                    "llm_model": settings.ollama_llm_model,
                    "fallback_models": settings.ollama_fallback_models(),
                    "embedding_model": settings.ollama_embedding_model,
                    "embedding_fallback_models": settings.ollama_embedding_fallback_model_list(),
                    "embedding_fallback": settings.ollama_embedding_fallback,
                },
                "config_key": "ollama",
            },
            {
                "id": "yandexgpt",
                "label": "YandexGPT (cloud)",
                "description": "Yandex Cloud Foundation Models (LLM + embeddings)",
                "available": settings.yandex_credentials_configured(),
                "models": YANDEX_MODELS,
                "default_model": settings.yandex_model,
                "config_key": "yandexgpt",
                "requires_env": ["YANDEX_FOLDER_ID", "YANDEX_API_KEY|YANDEX_PASSPORT_TOKEN"],
                "embeddings": {
                    "doc_model": settings.yandex_embedding_doc_model,
                    "query_model": settings.yandex_embedding_query_model,
                },
            },
        ],
    }


@router.get("/spec-levels")
async def get_spec_levels():
    return {
        "levels": [
            {"id": "L1", "name": "Brief", "time": "2–5 min", "description": "Outline only"},
            {
                "id": "L2",
                "name": "Standard",
                "time": "10–15 min",
                "description": "Core specs + 15–30 tasks",
            },
            {
                "id": "L3",
                "name": "Full",
                "time": "20–30 min",
                "description": "All artifacts + 50–100 tasks",
            },
            {
                "id": "L4",
                "name": "Exhaustive",
                "time": "Until approved",
                "description": "Dynamic pipeline, 100+ tasks, iterative review",
            },
        ]
    }
