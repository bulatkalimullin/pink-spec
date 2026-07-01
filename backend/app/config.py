"""Centralized environment configuration."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # Ollama
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    ollama_llm_model: str = Field(default="llama3.2", alias="OLLAMA_LLM_MODEL")
    ollama_llm_fallbacks: str = Field(default="", alias="OLLAMA_LLM_FALLBACKS")
    ollama_embedding_model: str = Field(default="nomic-embed-text", alias="OLLAMA_EMBEDDING_MODEL")
    ollama_embedding_fallback: Literal["keyword", "none"] = Field(
        default="keyword", alias="OLLAMA_EMBEDDING_FALLBACK"
    )

    @field_validator("ollama_embedding_fallback", mode="before")
    @classmethod
    def normalize_embedding_fallback(cls, v: object) -> str:
        if v is None or str(v).strip() == "":
            return "keyword"
        normalized = str(v).strip().lower()
        if normalized not in ("keyword", "none"):
            raise ValueError("OLLAMA_EMBEDDING_FALLBACK must be 'keyword' or 'none'")
        return normalized

    ollama_keep_alive: str = Field(default="5m", alias="OLLAMA_KEEP_ALIVE")
    ollama_timeout_sec: float = Field(default=120.0, alias="OLLAMA_TIMEOUT_SEC")
    ollama_port: int = Field(default=11434, alias="OLLAMA_PORT")

    # LLM generation
    llm_temperature: float = Field(default=0.2, alias="LLM_TEMPERATURE")
    llm_max_tokens: int = Field(default=4096, alias="LLM_MAX_TOKENS")

    # Storage
    sqlite_path: str = Field(default="./data/pink_spec.db", alias="SQLITE_PATH")
    vector_path: str = Field(default="./data/vectors", alias="VECTOR_PATH")
    output_path: str = Field(default="./output", alias="OUTPUT_PATH")

    # Monitoring defaults (session rules may override)
    monitor_interval_sec: int = Field(default=3, alias="MONITOR_INTERVAL_SEC")
    warn_cpu_pct: float = Field(default=90.0, alias="WARN_CPU_PCT")
    warn_ram_pct: float = Field(default=85.0, alias="WARN_RAM_PCT")
    warn_gpu_mem_pct: float = Field(default=90.0, alias="WARN_GPU_MEM_PCT")

    # Resilience defaults (session rules may override)
    agent_timeout_sec: int = Field(default=900, alias="AGENT_TIMEOUT_SEC")
    stuck_detection_sec: int = Field(default=600, alias="STUCK_DETECTION_SEC")
    hitl_timeout_sec: int = Field(default=7200, alias="HITL_TIMEOUT_SEC")

    def ollama_fallback_models(self) -> list[str]:
        return [m.strip() for m in self.ollama_llm_fallbacks.split(",") if m.strip()]

    def provider_cfg(self) -> dict[str, Any]:
        return {
            "ollama_base_url": self.ollama_base_url,
            "ollama_llm_model": self.ollama_llm_model,
            "ollama_llm_fallbacks": self.ollama_fallback_models(),
            "ollama_embedding_model": self.ollama_embedding_model or None,
            "ollama_embedding_fallback": self.ollama_embedding_fallback,
            "ollama_keep_alive": self.ollama_keep_alive,
            "ollama_timeout_sec": self.ollama_timeout_sec,
            "temperature": self.llm_temperature,
            "max_tokens": self.llm_max_tokens,
        }

    def monitoring_defaults(self) -> dict[str, Any]:
        return {
            "enabled": True,
            "interval_sec": self.monitor_interval_sec,
            "warn_cpu_pct": self.warn_cpu_pct,
            "warn_ram_pct": self.warn_ram_pct,
            "warn_gpu_mem_pct": self.warn_gpu_mem_pct,
            "show_per_core": False,
        }

    def resilience_defaults(self) -> dict[str, Any]:
        return {
            "agent_timeout_sec": self.agent_timeout_sec,
            "stuck_detection_sec": self.stuck_detection_sec,
            "hitl_timeout_sec": self.hitl_timeout_sec,
            "max_review_cycles": 10,
            "patch_unchanged_limit": 2,
            "review_plateau_window": 3,
            "circuit_breaker_failures": 3,
            "circuit_breaker_cooldown_sec": 60,
            "checkpoint_every_agent": True,
            "auto_resume_on_reconnect": True,
        }

    def public_dict(self) -> dict[str, Any]:
        """Safe snapshot for Settings UI (no secrets)."""
        return {
            "ollama_base_url": self.ollama_base_url,
            "ollama_llm_model": self.ollama_llm_model,
            "ollama_llm_fallbacks": self.ollama_llm_fallbacks,
            "ollama_embedding_model": self.ollama_embedding_model,
            "ollama_embedding_fallback": self.ollama_embedding_fallback,
            "ollama_keep_alive": self.ollama_keep_alive,
            "ollama_timeout_sec": self.ollama_timeout_sec,
            "llm_temperature": self.llm_temperature,
            "llm_max_tokens": self.llm_max_tokens,
            "monitor_interval_sec": self.monitor_interval_sec,
            "warn_cpu_pct": self.warn_cpu_pct,
            "warn_ram_pct": self.warn_ram_pct,
            "warn_gpu_mem_pct": self.warn_gpu_mem_pct,
            "agent_timeout_sec": self.agent_timeout_sec,
            "stuck_detection_sec": self.stuck_detection_sec,
            "hitl_timeout_sec": self.hitl_timeout_sec,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()
