"""Tests for Ollama presets and model install detection."""

from app.services.ollama_presets import (
    config_missing_models,
    enrich_presets,
    model_installed,
    preset_missing_models,
    preset_required_models,
)


def test_model_installed_normalizes_latest():
    installed = ["gemma3:4b", "nomic-embed-text:latest"]
    assert model_installed("gemma3:4b", installed)
    assert model_installed("nomic-embed-text", installed)


def test_preset_required_models_dedupes():
    cfg = enrich_presets([])[0]["config"]
    required = preset_required_models(cfg)
    assert "jayeshpandit2480/gemma3-UNCENSORED:4b" in required
    assert len(required) == len(set(required))


def test_preset_missing_models():
    installed = ["gemma3:4b", "gemma3:1b"]
    preset = enrich_presets(installed)[0]
    assert "jayeshpandit2480/gemma3-UNCENSORED:4b" in preset["missing_models"]
    assert preset["ready"] is False


def test_preset_ready_when_all_installed():
    installed = [
        "jayeshpandit2480/gemma3-UNCENSORED:4b",
        "gemma3:4b",
        "gemma3:1b",
        "locusai/all-minilm-l6-v2:latest",
        "embeddinggemma:latest",
    ]
    preset = enrich_presets(installed)[0]
    assert preset["missing_models"] == []
    assert preset["ready"] is True


def test_config_missing_models():
    installed = ["gemma3:4b"]
    missing = config_missing_models(
        {
            "llm_model": "qwen2.5:7b",
            "fallback_models": ["gemma3:4b"],
            "embedding_model": "nomic-embed-text",
            "embedding_fallback_models": [],
        },
        installed,
    )
    assert "qwen2.5:7b" in missing
    assert "nomic-embed-text" in missing
    assert "gemma3:4b" not in missing


def test_ultra_light_preset_ready_on_minimal_install():
    installed = ["gemma3:1b", "gemma3:4b", "locusai/all-minilm-l6-v2:latest"]
    presets = {p["id"]: p for p in enrich_presets(installed)}
    assert presets["ultra_light"]["ready"] is True
    assert presets["ultra_light"]["config"]["llm_model"] == "gemma3:1b"


def test_max_aggressive_preset_ready_with_user_models():
    installed = [
        "dzgg/Qwen3.5-Uncensored-HauhauCS-Aggressive:4b",
        "jayeshpandit2480/gemma3-UNCENSORED:4b",
        "project-qwen3.5-4b-uncensored-hauhaucs-aggressive-q4_k_m:latest",
        "gemma3:4b",
        "gemma3:1b",
        "nomic-embed-text:latest",
        "embeddinggemma:latest",
        "locusai/all-minilm-l6-v2:latest",
    ]
    presets = {p["id"]: p for p in enrich_presets(installed)}
    assert presets["max_aggressive"]["ready"] is True
    assert presets["max_aggressive"]["config"]["embedding_model"] == "nomic-embed-text:latest"
