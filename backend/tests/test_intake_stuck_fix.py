"""Regression tests for intake + watchdog stuck handling."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.services.session_runner import SessionRunner
from app.services.session_watchdog import SessionState


def test_intake_agent_not_flagged_as_stuck_during_slow_llm():
    state = SessionState(
        session_id="s1",
        stuck_detection_sec=60,
        current_agent="intake",
        last_progress_at=time.time() - 120,
        status="running",
    )
    assert state.is_stuck() is False


def test_intake_agent_not_subject_to_agent_timeout():
    state = SessionState(
        session_id="s1",
        current_agent="intake",
        agent_started_at=time.time() - 999,
    )
    assert state.is_agent_timed_out() is False


def test_waiting_user_not_stuck():
    state = SessionState(
        session_id="s1",
        stuck_detection_sec=1,
        last_progress_at=time.time() - 60,
        status="waiting_user",
    )
    assert state.is_stuck() is False


def test_retry_agent_cancel_does_not_set_graph_cancel_event():
    runner = SessionRunner()

    async def _hang(cancel_event: asyncio.Event) -> None:
        await asyncio.sleep(10)

    async def _run() -> None:
        await runner.start("sess-1", _hang)
        assert runner.cancel_agent("sess-1") is True
        run = runner.get("sess-1")
        assert run is not None
        assert not run.cancel_event.is_set()

    asyncio.run(_run())


def test_request_cancel_sets_graph_cancel_event():
    runner = SessionRunner()

    async def _hang(cancel_event: asyncio.Event) -> None:
        await asyncio.sleep(10)

    async def _run() -> None:
        await runner.start("sess-2", _hang)
        assert runner.request_cancel("sess-2") is True
        run = runner.get("sess-2")
        assert run is not None
        assert run.cancel_event.is_set()

    asyncio.run(_run())


def test_clear_cancel_resets_flag():
    runner = SessionRunner()

    async def _hang(cancel_event: asyncio.Event) -> None:
        await asyncio.sleep(10)

    async def _run() -> None:
        await runner.start("sess-3", _hang)
        runner.request_cancel("sess-3")
        runner.clear_cancel("sess-3")
        run = runner.get("sess-3")
        assert run is not None
        assert not run.cancel_event.is_set()

    asyncio.run(_run())
