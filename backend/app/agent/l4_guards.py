"""L4 runtime guards — model/token checks and tasks_per_batch tuning."""

from __future__ import annotations

import re
from typing import Any


def is_small_llm_model(model_name: str) -> bool:
    """Heuristic: models ≤4B params struggle with L4 JSON/review workloads."""
    m = (model_name or "").lower()
    if re.search(r":[1234]b\b", m):
        return True
    if re.search(r"\b[1234]b\b", m):
        return True
    return False


def apply_l4_runtime_guards(
    rules: dict[str, Any],
    *,
    global_llm_max_tokens: int | None = None,
    active_llm_model: str | None = None,
) -> tuple[dict[str, Any], list[str]]:
    """
    Apply L4-specific runtime adjustments to rules dict.
    Returns (updated_rules, warning_messages).
    """
    if rules.get("spec_level") != "L4":
        return rules, []

    rules = dict(rules)
    warnings: list[str] = []
    ollama = dict(rules.get("ollama") or {})
    l4 = dict(rules.get("l4") or {})

    if ollama.get("max_tokens", 4096) < 8192:
        ollama["max_tokens"] = 8192
    if ollama.get("timeout_sec", 120) < 300:
        ollama["timeout_sec"] = 300

    effective_tokens = int(ollama.get("max_tokens", 8192))
    llm_provider = str(rules.get("llm_provider", "ollama"))
    if llm_provider == "yandexgpt":
        yandex = dict(rules.get("yandexgpt") or {})
        model = str(yandex.get("model") or active_llm_model or "")
        if yandex.get("max_tokens") is not None:
            effective_tokens = int(yandex["max_tokens"])
    else:
        model = str(ollama.get("llm_model") or active_llm_model or "")

    if global_llm_max_tokens is not None and global_llm_max_tokens < 8192:
        warnings.append(
            f"Global LLM_MAX_TOKENS={global_llm_max_tokens} < 8192. "
            "Set LLM_MAX_TOKENS=8192 in .env for reliable L4 output."
        )

    if is_small_llm_model(model):
        warnings.append(
            f"L4 with small model {model!r} may finish as completed_partial. "
            "Consider a 7B+ model (e.g. qwen2.5:7b)."
        )

    batch = int(l4.get("tasks_per_batch", 25))
    if is_small_llm_model(model) or effective_tokens < 4096:
        if batch > 12:
            l4["tasks_per_batch"] = 12
            warnings.append("L4 tasks_per_batch reduced to 12 (small model or low max_tokens).")
    elif effective_tokens < 8192 and batch > 15:
        l4["tasks_per_batch"] = 15
        warnings.append("L4 tasks_per_batch reduced to 15 (max_tokens < 8192).")

    rules["ollama"] = ollama
    rules["l4"] = l4
    return rules, warnings
