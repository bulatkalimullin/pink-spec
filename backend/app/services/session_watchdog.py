"""Session Watchdog — detects stuck sessions and manages circuit breakers."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class CircuitBreaker:
    agent_id: str
    failure_threshold: int = 3
    cooldown_sec: int = 60
    failures: int = 0
    opened_at: float | None = None

    def is_open(self) -> bool:
        if self.opened_at is None:
            return False
        if time.time() - self.opened_at >= self.cooldown_sec:
            self.failures = 0
            self.opened_at = None
            return False
        return True

    def record_failure(self) -> bool:
        """Returns True if circuit just opened."""
        self.failures += 1
        if self.failures >= self.failure_threshold and self.opened_at is None:
            self.opened_at = time.time()
            return True
        return False

    def record_success(self) -> None:
        self.failures = 0
        self.opened_at = None


@dataclass
class SessionState:
    session_id: str
    started_at: float = field(default_factory=time.time)
    last_progress_at: float = field(default_factory=time.time)
    current_agent: str = "supervisor"
    agent_started_at: float = field(default_factory=time.time)
    stuck_detection_sec: int = 300
    agent_timeout_sec: int = 600
    max_review_cycles: int = 10
    review_cycles: int = 0
    circuit_breakers: dict[str, CircuitBreaker] = field(default_factory=dict)
    cb_threshold: int = 3
    cb_cooldown_sec: int = 60
    status: str = "running"
    stuck_detected_at: float | None = None

    def mark_agent_started(self, agent_id: str) -> None:
        """Record real agent work start (not supervisor-only iterations)."""
        self.current_agent = agent_id
        self.agent_started_at = time.time()
        self.last_progress_at = time.time()

    def mark_agent_completed(self) -> None:
        """Record successful agent completion."""
        self.last_progress_at = time.time()

    def is_stuck(self) -> bool:
        """True when no progress for stuck_detection_sec while session is active."""
        if self.status in ("failed", "paused", "completed", "completed_partial"):
            return False
        if self.status == "stuck":
            return True
        if self.status not in ("running", "degraded"):
            return False
        return (time.time() - self.last_progress_at) > self.stuck_detection_sec

    def stuck_since_sec(self) -> int | None:
        if self.status == "stuck" and self.stuck_detected_at:
            return int(time.time() - self.stuck_detected_at)
        if self.is_stuck() and self.status in ("running", "degraded"):
            return int(time.time() - self.last_progress_at)
        return None

    def is_agent_timed_out(self) -> bool:
        if self.current_agent in ("supervisor", "export"):
            return False
        return (time.time() - self.agent_started_at) > self.agent_timeout_sec

    def get_circuit_breaker(self, agent_id: str) -> CircuitBreaker:
        if agent_id not in self.circuit_breakers:
            self.circuit_breakers[agent_id] = CircuitBreaker(
                agent_id=agent_id,
                failure_threshold=self.cb_threshold,
                cooldown_sec=self.cb_cooldown_sec,
            )
        return self.circuit_breakers[agent_id]


class SessionWatchdog:
    """Polls session states; emits stuck / timeout / circuit_breaker events via LogBus."""

    POLL_INTERVAL = 10.0

    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}
        self._answer_waiters: dict[str, asyncio.Future] = {}
        self._on_stuck_callbacks: list[Callable] = []

    def register(self, session_id: str, resilience_cfg: dict) -> SessionState:
        state = SessionState(
            session_id=session_id,
            stuck_detection_sec=resilience_cfg.get("stuck_detection_sec", 300),
            agent_timeout_sec=resilience_cfg.get("agent_timeout_sec", 600),
            max_review_cycles=resilience_cfg.get("max_review_cycles", 10),
            cb_threshold=resilience_cfg.get("circuit_breaker_failures", 3),
            cb_cooldown_sec=resilience_cfg.get("circuit_breaker_cooldown_sec", 60),
        )
        self._sessions[session_id] = state
        return state

    def unregister(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    def get_state(self, session_id: str) -> SessionState | None:
        return self._sessions.get(session_id)

    def on_stuck(self, callback: Callable) -> None:
        self._on_stuck_callbacks.append(callback)

    async def wait_for_answer(self, session_id: str, question_id: str, timeout_sec: int) -> object:
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._answer_waiters[question_id] = future
        try:
            return await asyncio.wait_for(future, timeout=timeout_sec)
        except TimeoutError:
            return None
        finally:
            self._answer_waiters.pop(question_id, None)

    def deliver_answer(self, question_id: str, answer: object) -> None:
        future = self._answer_waiters.get(question_id)
        if future and not future.done():
            future.set_result(answer)

    async def _notify_stuck(self, session_id: str, state: SessionState, reason: str) -> None:
        from app.services.log_bus import log_bus
        from app.services.session import update_session_status

        if state.stuck_detected_at is None:
            state.stuck_detected_at = time.time()
        state.status = "stuck"
        since_sec = state.stuck_since_sec() or 0

        await update_session_status(session_id, "stuck")
        await log_bus.emit(
            session_id,
            "session_stuck",
            {
                "reason": reason,
                "since_sec": since_sec,
                "suggested_actions": ["retry_agent", "skip_agent", "force_export"],
            },
        )
        for cb in self._on_stuck_callbacks:
            try:
                result = cb(session_id, reason)
                if asyncio.iscoroutine(result):
                    await result
            except Exception:
                logger.exception("on_stuck_callback_failed", session_id=session_id)

    async def run(self) -> None:
        """Background polling loop."""
        while True:
            await asyncio.sleep(self.POLL_INTERVAL)
            from app.services.log_bus import log_bus

            for session_id, state in list(self._sessions.items()):
                if state.status in ("failed", "paused", "completed", "completed_partial"):
                    continue
                if state.status == "stuck":
                    continue

                if state.is_agent_timed_out():
                    logger.warning(
                        "agent_timeout", session_id=session_id, agent=state.current_agent
                    )
                    await log_bus.emit(
                        session_id,
                        "agent_timeout",
                        {"agent_id": state.current_agent, "timeout_sec": state.agent_timeout_sec},
                    )
                    await self._notify_stuck(session_id, state, "agent_timeout")

                elif state.is_stuck():
                    elapsed = int(time.time() - state.last_progress_at)
                    logger.warning("session_stuck", session_id=session_id, since_sec=elapsed)
                    await self._notify_stuck(session_id, state, "no_progress")


watchdog = SessionWatchdog()
