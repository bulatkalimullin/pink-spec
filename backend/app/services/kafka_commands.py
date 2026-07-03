"""Helpers for publishing session commands from API routes."""

from __future__ import annotations

from typing import Any

from app.kafka.command_producer import command_producer
from app.kafka.schemas import CommandType, SessionCommand


async def publish_start(
    session_id: str, *, idea: str, rules: dict[str, Any], monitoring: dict[str, Any]
) -> SessionCommand:
    cmd = SessionCommand(
        type=CommandType.session_start,
        session_id=session_id,
        payload={"idea": idea, "rules": rules, "monitoring": monitoring},
    )
    await command_producer.publish(cmd)
    return cmd


async def publish_restart(
    session_id: str, *, idea: str, rules: dict[str, Any], monitoring: dict[str, Any]
) -> SessionCommand:
    cmd = SessionCommand(
        type=CommandType.session_restart,
        session_id=session_id,
        payload={"idea": idea, "rules": rules, "monitoring": monitoring},
    )
    await command_producer.publish(cmd)
    return cmd


async def publish_cancel(session_id: str) -> SessionCommand:
    cmd = SessionCommand(type=CommandType.session_cancel, session_id=session_id)
    await command_producer.publish(cmd)
    return cmd


async def publish_control(session_id: str, payload: dict[str, Any]) -> SessionCommand:
    cmd = SessionCommand(
        type=CommandType.session_control,
        session_id=session_id,
        payload=payload,
    )
    await command_producer.publish(cmd)
    return cmd


async def publish_intake_answers_ready(session_id: str, answers_count: int) -> SessionCommand:
    cmd = SessionCommand(
        type=CommandType.intake_answers_ready,
        session_id=session_id,
        payload={"answers_count": answers_count},
    )
    await command_producer.publish(cmd)
    return cmd


async def publish_rag_ingest(
    session_id: str, *, temp_paths: list[str], sources_meta: list[dict[str, Any]]
) -> SessionCommand:
    cmd = SessionCommand(
        type=CommandType.rag_ingest,
        session_id=session_id,
        payload={"temp_paths": temp_paths, "sources_meta": sources_meta},
    )
    await command_producer.publish(cmd)
    return cmd
