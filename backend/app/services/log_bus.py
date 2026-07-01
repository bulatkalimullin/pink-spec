"""LogBus — async broadcast of all WS events to connected clients + SQLite persistence."""
from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import structlog

from app.db.connection import get_db

logger = structlog.get_logger(__name__)


class LogBus:
    """Central event bus. Agents emit events; LogBus fans out to WS subscribers and DB."""

    def __init__(self) -> None:
        # session_id → set of asyncio.Queue (one per WS connection)
        self._subscribers: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self._seq_counters: dict[str, int] = defaultdict(int)
        self._persist_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=10_000)

    # --- Subscription management ---

    def subscribe(self, session_id: str) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=5_000)
        self._subscribers[session_id].add(q)
        return q

    def unsubscribe(self, session_id: str, q: asyncio.Queue) -> None:
        self._subscribers[session_id].discard(q)

    # --- Event emission ---

    async def emit(self, session_id: str, event_type: str, payload: dict[str, Any]) -> None:
        seq = self._next_seq(session_id)
        envelope = {
            "type": event_type,
            "ts": datetime.now(timezone.utc).isoformat(),
            "seq": seq,
            "session_id": session_id,
            "payload": payload,
        }
        await self._broadcast(session_id, envelope)
        await self._enqueue_persist(envelope)

    def emit_sync(self, session_id: str, event_type: str, payload: dict[str, Any]) -> None:
        """Fire-and-forget from sync context (runs emit as task)."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(self.emit(session_id, event_type, payload))
        except RuntimeError:
            pass

    # --- Broadcast ---

    async def _broadcast(self, session_id: str, envelope: dict[str, Any]) -> None:
        dead: list[asyncio.Queue] = []
        for q in list(self._subscribers.get(session_id, [])):
            try:
                q.put_nowait(envelope)
            except asyncio.QueueFull:
                dead.append(q)
                logger.warning("ws_queue_full", session_id=session_id)
        for q in dead:
            self._subscribers[session_id].discard(q)

    # --- Persistence ---

    async def _enqueue_persist(self, envelope: dict[str, Any]) -> None:
        # system_metrics events are not persisted (high-frequency noise)
        if envelope["type"] == "system_metrics":
            return
        try:
            self._persist_queue.put_nowait(envelope)
        except asyncio.QueueFull:
            logger.warning("persist_queue_full")

    async def run_persist_worker(self) -> None:
        """Background task: drains persist_queue → SQLite in batches."""
        while True:
            batch: list[dict[str, Any]] = []
            try:
                envelope = await asyncio.wait_for(self._persist_queue.get(), timeout=1.0)
                batch.append(envelope)
                # drain up to 50 more without waiting
                while not self._persist_queue.empty() and len(batch) < 50:
                    batch.append(self._persist_queue.get_nowait())
            except TimeoutError:
                await asyncio.sleep(0.1)
                continue

            try:
                async with get_db() as db:
                    await db.executemany(
                        "INSERT INTO session_logs (session_id, seq, type, ts, payload_json) "
                        "VALUES (?, ?, ?, ?, ?)",
                        [
                            (
                                e["session_id"],
                                e["seq"],
                                e["type"],
                                e["ts"],
                                json.dumps(e["payload"]),
                            )
                            for e in batch
                        ],
                    )
                    await db.commit()
            except Exception:
                logger.exception("persist_worker_error")

    def _next_seq(self, session_id: str) -> int:
        self._seq_counters[session_id] += 1
        return self._seq_counters[session_id]

    async def get_log_history(
        self, session_id: str, from_seq: int = 0, limit: int = 500
    ) -> list[dict[str, Any]]:
        async with get_db() as db:
            cursor = await db.execute(
                "SELECT seq, type, ts, payload_json FROM session_logs "
                "WHERE session_id = ? AND seq > ? ORDER BY seq LIMIT ?",
                (session_id, from_seq, limit),
            )
            rows = await cursor.fetchall()
        return [
            {
                "seq": r["seq"],
                "type": r["type"],
                "ts": r["ts"],
                "payload": json.loads(r["payload_json"]),
            }
            for r in rows
        ]


# Singleton
log_bus = LogBus()
