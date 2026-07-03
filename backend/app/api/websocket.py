"""WebSocket handler — subscribes to LogBus and streams events to the client."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from app.services.kafka_commands import publish_cancel, publish_control
from app.services.log_bus import log_bus
from app.services.session import answer_question, get_session, update_session_status

logger = structlog.get_logger(__name__)

HEARTBEAT_INTERVAL = 30
RECONNECT_LOG_TAIL = 200


async def ws_session_handler(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    logger.info("ws_connected", session_id=session_id)

    q = log_bus.subscribe(session_id)

    session = await get_session(session_id)
    if session:
        history = await log_bus.get_log_history(session_id, from_seq=0, limit=RECONNECT_LOG_TAIL)
        await websocket.send_text(
            json.dumps(
                {
                    "type": "session_snapshot",
                    "ts": datetime.now(UTC).isoformat(),
                    "session_id": session_id,
                    "payload": {
                        "status": session.get("status"),
                        "log_tail": history,
                    },
                }
            )
        )

    async def heartbeat() -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL)
            try:
                await websocket.send_text(json.dumps({"type": "ping", "session_id": session_id}))
            except Exception:
                break

    async def sender() -> None:
        while True:
            try:
                envelope = await asyncio.wait_for(q.get(), timeout=60.0)
                await websocket.send_text(json.dumps(envelope, default=str))
            except TimeoutError:
                continue
            except Exception:
                break

    async def receiver() -> None:
        while True:
            try:
                raw = await websocket.receive_text()
                msg = json.loads(raw)
                await _handle_client_message(session_id, msg)
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.warning("ws_receive_error", error=str(e))

    tasks = [
        asyncio.create_task(sender()),
        asyncio.create_task(receiver()),
        asyncio.create_task(heartbeat()),
    ]

    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
        log_bus.unsubscribe(session_id, q)
        logger.info("ws_disconnected", session_id=session_id)


async def _handle_client_message(session_id: str, msg: dict) -> None:
    msg_type = msg.get("type")

    if msg_type == "answer":
        question_id = msg.get("question_id", "")
        answer = msg.get("answer")
        await answer_question(session_id, question_id, answer)

    elif msg_type == "cancel":
        await publish_cancel(session_id)
        await log_bus.emit(
            session_id,
            "log_entry",
            {"level": "warn", "agent_id": "system", "message": "Session cancel queued"},
        )

    elif msg_type == "pause":
        await publish_control(session_id, {"action": "pause"})
        await update_session_status(session_id, "paused")
        await log_bus.emit(
            session_id,
            "log_entry",
            {"level": "info", "agent_id": "system", "message": "Session paused by user"},
        )

    elif msg_type == "resume":
        await publish_control(session_id, {"action": "resume"})
        await update_session_status(session_id, "running")
        await log_bus.emit(
            session_id,
            "log_entry",
            {"level": "info", "agent_id": "system", "message": "Session resumed by user"},
        )

    elif msg_type == "request_snapshot":
        session = await get_session(session_id)
        history = await log_bus.get_log_history(
            session_id, from_seq=msg.get("from_seq", 0), limit=500
        )
        await log_bus.emit(
            session_id,
            "session_snapshot",
            {
                "status": session.get("status") if session else "unknown",
                "log_tail": history,
            },
        )
