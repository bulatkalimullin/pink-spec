"""Pre-flight intake — batch questions before the main agent graph runs."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

import structlog

from app.agent.state import MultiAgentState
from app.services.artifact_quality import inject_nfr_from_intake
from app.services.log_bus import log_bus
from app.services.session import get_open_questions, save_question, update_session_status

logger = structlog.get_logger(__name__)

_intake_events: dict[str, asyncio.Event] = {}


def intake_event(session_id: str) -> asyncio.Event:
    if session_id not in _intake_events:
        _intake_events[session_id] = asyncio.Event()
    return _intake_events[session_id]


def clear_intake_event(session_id: str) -> None:
    _intake_events.pop(session_id, None)


def notify_intake_resolved(session_id: str) -> None:
    intake_event(session_id).set()


def merge_answers_into_state(
    state: MultiAgentState, qa_rows: list[dict[str, Any]]
) -> MultiAgentState:
    """Append user clarifications to idea context for downstream agents."""
    if not qa_rows:
        return {**state, "intake_complete": True}

    answers: dict[str, Any] = {}
    lines = ["[User clarifications]"]
    for row in qa_rows:
        qid = row["id"]
        text = row.get("text", qid)
        answer = row.get("answer")
        answers[qid] = answer
        lines.append(f"- Q: {text}\n  A: {answer}")

    block = "\n".join(lines)
    idea = state.get("idea", "")
    if block not in idea:
        idea = f"{idea.rstrip()}\n\n{block}"

    rules = dict(state.get("rules") or {})
    output = dict(rules.get("output") or {})
    if output.get("language") and not output.get("ui_language"):
        output["ui_language"] = output["language"]
    rules["output"] = output
    rules = inject_nfr_from_intake(rules, idea, answers)

    ctx = dict(state.get("context", {}) or {})
    summaries = list(ctx.get("turn_summaries", []))
    summaries.append(block)
    ctx["turn_summaries"] = summaries[-10:]
    ctx["phase_summary"] = block

    return {
        **state,
        "idea": idea,
        "context": ctx,
        "intake_answers": {**state.get("intake_answers", {}), **answers},
        "intake_complete": True,
        "rules": rules,
    }


async def load_answered_qa(session_id: str) -> list[dict[str, Any]]:
    from app.db.connection import get_db

    async with get_db() as db:
        cursor = await db.execute(
            "SELECT id, text, answer_json FROM open_questions "
            "WHERE session_id = ? AND answered_at IS NOT NULL ORDER BY created_at",
            (session_id,),
        )
        rows = await cursor.fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        d = dict(row)
        raw = d.get("answer_json")
        if not raw:
            continue
        try:
            answer = json.loads(raw)
        except json.JSONDecodeError:
            answer = raw
        result.append({"id": d["id"], "text": d.get("text", ""), "answer": answer})
    return result


async def run_intake_phase(
    state: MultiAgentState,
    llm_provider,
) -> tuple[MultiAgentState, bool]:
    """
    Run intake analysis. Returns (state, proceed).
    proceed=False means graph must wait for user answers.
    """
    rules = state.get("rules", {}) or {}
    hitl = rules.get("hitl", {}) or {}
    if not hitl.get("enabled", True) or not hitl.get("intake_before_start", True):
        return {**state, "intake_complete": True}, True

    session_id = state["session_id"]
    open_qs = await get_open_questions(session_id)
    if open_qs:
        await update_session_status(session_id, "waiting_user")
        await log_bus.emit(
            session_id,
            "intake_waiting",
            {"questions_count": len(open_qs), "resumed": True},
        )
        return state, False

    from app.agent.agents.intake_agent import IntakeAgent

    agent = IntakeAgent(llm=llm_provider)
    result = await agent.analyze(state)

    if result.get("ready") or not result.get("questions"):
        await log_bus.emit(
            session_id,
            "intake_complete",
            {"ready": True, "summary": result.get("summary", "Sufficient context")},
        )
        return {**state, "intake_complete": True}, True

    questions = result["questions"]
    for q in questions:
        await save_question(
            session_id,
            q["id"],
            q["text"],
            q.get("options") or [],
            q.get("priority", "high"),
        )

    state = {
        **state,
        "status": "waiting_user",
        "open_questions": [
            {
                "id": q["id"],
                "text": q["text"],
                "priority": q.get("priority", "high"),
                "options": q.get("options") or [],
                "required": q.get("required", True),
            }
            for q in questions
        ],
        "intake_complete": False,
    }

    await update_session_status(session_id, "waiting_user")
    intake_event(session_id).clear()

    await log_bus.emit(
        session_id,
        "intake_started",
        {
            "summary": result.get("summary", ""),
            "questions": state["open_questions"],
            "questions_count": len(questions),
        },
    )
    for q in questions:
        await log_bus.emit(
            session_id,
            "question_asked",
            {
                "question_id": q["id"],
                "text": q["text"],
                "options": q.get("options") or [],
                "priority": q.get("priority", "high"),
            },
        )

    await log_bus.emit(
        session_id,
        "log_entry",
        {
            "level": "info",
            "agent_id": "intake",
            "message": _intake_waiting_message(rules, len(questions)),
        },
    )
    return state, False


def _intake_waiting_message(rules: dict, count: int) -> str:
    lang = str((rules.get("output") or {}).get("language", "en")).lower()
    if lang == "ru":
        return (
            f"Нужен ваш ввод: {count} вопрос(ов). "
            "Ответьте на все в панели «Вопросы», затем пайплайн запустится."
        )
    return (
        f"Need your input: {count} question(s). "
        "Answer all in the Questions panel, then the pipeline will start."
    )


async def wait_for_intake_answers(
    session_id: str, timeout_sec: int, watchdog=None
) -> bool:
    """Block until all open questions are answered or timeout."""
    event = intake_event(session_id)

    async def _poll_open() -> bool:
        while True:
            open_qs = await get_open_questions(session_id)
            if not open_qs:
                return True
            if event.is_set():
                open_qs = await get_open_questions(session_id)
                return not open_qs
            if watchdog:
                wd = watchdog.get_state(session_id)
                if wd:
                    wd.status = "waiting_user"
                    wd.last_progress_at = time.time()
            await asyncio.sleep(1.0)

    try:
        return await asyncio.wait_for(_poll_open(), timeout=timeout_sec)
    except TimeoutError:
        logger.warning("intake_timeout", session_id=session_id, timeout_sec=timeout_sec)
        return False
