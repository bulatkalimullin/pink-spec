"""Session lifecycle — one asyncio.Task per session with cancellation support."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class SessionRun:
    session_id: str
    task: asyncio.Task
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    agent_task: asyncio.Task | None = None


class SessionRunner:
    """Registry of active session graph tasks."""

    def __init__(self) -> None:
        self._runs: dict[str, SessionRun] = {}

    def get(self, session_id: str) -> SessionRun | None:
        return self._runs.get(session_id)

    def is_running(self, session_id: str) -> bool:
        run = self._runs.get(session_id)
        return run is not None and not run.task.done()

    async def start(
        self,
        session_id: str,
        coro_factory,
    ) -> SessionRun:
        if self.is_running(session_id):
            raise RuntimeError(f"Session {session_id} already running")

        cancel_event = asyncio.Event()
        task = asyncio.create_task(coro_factory(cancel_event), name=f"graph-{session_id[:8]}")
        run = SessionRun(session_id=session_id, task=task, cancel_event=cancel_event)
        self._runs[session_id] = run

        def _done_callback(t: asyncio.Task) -> None:
            self._runs.pop(session_id, None)

        task.add_done_callback(_done_callback)
        return run

    def cancel_agent(self, session_id: str) -> bool:
        """Interrupt the running agent without shutting down the graph."""
        run = self._runs.get(session_id)
        if not run:
            return False
        if run.agent_task and not run.agent_task.done():
            run.agent_task.cancel()
        return True

    def clear_cancel(self, session_id: str) -> None:
        run = self._runs.get(session_id)
        if run:
            run.cancel_event.clear()

    def request_cancel(self, session_id: str) -> bool:
        """Request graceful graph shutdown (export / degraded exit)."""
        run = self._runs.get(session_id)
        if not run:
            return False
        run.cancel_event.set()
        self.cancel_agent(session_id)
        return True

    def set_agent_task(self, session_id: str, agent_task: asyncio.Task | None) -> None:
        run = self._runs.get(session_id)
        if run:
            run.agent_task = agent_task

    async def cancel(self, session_id: str) -> bool:
        if not self.request_cancel(session_id):
            return False
        run = self._runs.get(session_id)
        if run and not run.task.done():
            run.task.cancel()
            try:
                await run.task
            except asyncio.CancelledError:
                pass
        return True


session_runner = SessionRunner()
