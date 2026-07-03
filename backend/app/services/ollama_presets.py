"""Ollama model presets and install-status helpers."""

from __future__ import annotations

from typing import Any, TypedDict


class OllamaPresetConfig(TypedDict):
    llm_model: str
    fallback_models: list[str]
    embedding_model: str
    embedding_fallback_models: list[str]
    embedding_fallback: str


class OllamaPresetDef(TypedDict):
    id: str
    label: str
    description: str
    config: OllamaPresetConfig


OLLAMA_LLM_HINTS = [
    "qwen2.5:7b",
    "gemma3:4b",
    "gemma3:1b",
    "jayeshpandit2480/gemma3-UNCENSORED:4b",
    "llama3.2",
    "mistral",
]

OLLAMA_EMBEDDING_HINTS = [
    "nomic-embed-text",
    "locusai/all-minilm-l6-v2:latest",
    "embeddinggemma:latest",
]

EMBEDDING_FALLBACK_OPTIONS = [
    {"value": "keyword", "label": "BM25 keyword"},
    {"value": "none", "label": "No fallback — error on failure"},
]

OLLAMA_PRESETS: list[OllamaPresetDef] = [
    {
        "id": "uncensored_4b",
        "label": "Uncensored 4B (6GB GPU)",
        "description": "Uncensored Gemma3 4B with compact embeddings for RTX 3050-class GPUs",
        "config": {
            "llm_model": "jayeshpandit2480/gemma3-UNCENSORED:4b",
            "fallback_models": ["gemma3:4b", "gemma3:1b"],
            "embedding_model": "locusai/all-minilm-l6-v2:latest",
            "embedding_fallback_models": ["embeddinggemma:latest"],
            "embedding_fallback": "keyword",
        },
    },
    {
        "id": "balanced_7b",
        "label": "Balanced 7B",
        "description": "Higher quality LLM with 4B fallback; needs more VRAM",
        "config": {
            "llm_model": "qwen2.5:7b",
            "fallback_models": ["gemma3:4b"],
            "embedding_model": "nomic-embed-text",
            "embedding_fallback_models": ["locusai/all-minilm-l6-v2:latest"],
            "embedding_fallback": "keyword",
        },
    },
    {
        "id": "light_4b",
        "label": "Light 4B",
        "description": "Fast generation on modest hardware",
        "config": {
            "llm_model": "gemma3:4b",
            "fallback_models": ["gemma3:1b"],
            "embedding_model": "locusai/all-minilm-l6-v2:latest",
            "embedding_fallback_models": [],
            "embedding_fallback": "keyword",
        },
    },
    {
        "id": "rag_compact",
        "label": "RAG compact",
        "description": "Small embedding models for local RAG with minimal VRAM",
        "config": {
            "llm_model": "gemma3:4b",
            "fallback_models": ["gemma3:1b"],
            "embedding_model": "locusai/all-minilm-l6-v2:latest",
            "embedding_fallback_models": ["embeddinggemma:latest", "nomic-embed-text"],
            "embedding_fallback": "keyword",
        },
    },
]


def _normalize_model_name(name: str) -> str:
    """Strip :latest for comparison; keep other tags."""
    n = name.strip()
    if n.endswith(":latest"):
        return n[: -len(":latest")]
    return n


def model_installed(name: str, installed: list[str]) -> bool:
    """Check if a model name matches any installed Ollama tag."""
    if not name:
        return False
    target = _normalize_model_name(name)
    for item in installed:
        if _normalize_model_name(item) == target:
            return True
        if item == name or item.startswith(f"{target}:"):
            return True
    return False


def preset_required_models(config: OllamaPresetConfig) -> list[str]:
    """All LLM and embedding models referenced by a preset."""
    models: list[str] = []
    seen: set[str] = set()
    for raw in [
        config["llm_model"],
        *config.get("fallback_models", []),
        config["embedding_model"],
        *config.get("embedding_fallback_models", []),
    ]:
        if not raw:
            continue
        name = str(raw).strip()
        if name in seen:
            continue
        seen.add(name)
        models.append(name)
    return models


def preset_missing_models(config: OllamaPresetConfig, installed: list[str]) -> list[str]:
    return [m for m in preset_required_models(config) if not model_installed(m, installed)]


def enrich_presets(installed: list[str]) -> list[dict[str, Any]]:
    """Attach missing_models and ready flag to each preset."""
    result: list[dict[str, Any]] = []
    for preset in OLLAMA_PRESETS:
        missing = preset_missing_models(preset["config"], installed)
        result.append(
            {
                "id": preset["id"],
                "label": preset["label"],
                "description": preset["description"],
                "config": dict(preset["config"]),
                "missing_models": missing,
                "ready": len(missing) == 0,
            }
        )
    return result


def config_missing_models(config: dict[str, Any], installed: list[str]) -> list[str]:
    """Missing models for an arbitrary ollama rules config."""
    typed: OllamaPresetConfig = {
        "llm_model": str(config.get("llm_model") or ""),
        "fallback_models": list(config.get("fallback_models") or []),
        "embedding_model": str(config.get("embedding_model") or ""),
        "embedding_fallback_models": list(config.get("embedding_fallback_models") or []),
        "embedding_fallback": str(config.get("embedding_fallback") or "keyword"),
    }
    return preset_missing_models(typed, installed)
