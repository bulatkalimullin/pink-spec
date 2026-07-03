"""Kafka connection settings."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class KafkaSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    bootstrap_servers: str = Field(
        default="localhost:9092", alias="KAFKA_BOOTSTRAP_SERVERS"
    )
    commands_topic: str = Field(
        default="pink-spec.session.commands", alias="KAFKA_COMMANDS_TOPIC"
    )
    events_topic: str = Field(
        default="pink-spec.session.events", alias="KAFKA_EVENTS_TOPIC"
    )
    worker_group: str = Field(default="pink-spec-workers", alias="KAFKA_WORKER_GROUP")
    api_events_group: str = Field(
        default="pink-spec-api-events", alias="KAFKA_API_EVENTS_GROUP"
    )
    service_role: str = Field(default="api", alias="PINK_SPEC_SERVICE_ROLE")


@lru_cache
def kafka_settings() -> KafkaSettings:
    return KafkaSettings()
