"""Session REST routes."""

from __future__ import annotations

import asyncio

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import PlainTextResponse, Response

from app.schemas.rules import (
    AnswerRequest,
    BatchAnswersRequest,
    RecoverRequest,
    SessionControlRequest,
    StartSessionRequest,
)
from app.services.export import build_zip, read_artifact, read_task_file, session_output_dir
from app.services.log_bus import log_bus
from app.services.session import (
    answer_question,
    create_session,
    get_latest_checkpoint,
    get_open_questions,
    get_session,
)
from app.services.session_control import enqueue, get_overrides, set_overrides
from app.services.session_watchdog import watchdog

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


def _get_providers():
    """Lazy import to avoid circular at startup."""
    from app.main import embedding_provider, llm_provider  # type: ignore

    return llm_provider, embedding_provider


@router.post("", status_code=201)
async def create_session_endpoint(body: StartSessionRequest):
    rules_dict = body.rules.model_dump()
    session_id = await create_session(
        spec_level=body.rules.spec_level.value,
        idea=body.idea,
        rules=rules_dict,
    )
    return {"session_id": session_id, "spec_level": body.rules.spec_level}


@router.post("/{session_id}/start")
async def start_session(
    session_id: str, body: StartSessionRequest, background_tasks: BackgroundTasks
):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session["status"] not in ("pending", "failed"):
        raise HTTPException(409, f"Session already in state: {session['status']}")

    from app.services.session_launcher import launch_session_graph

    rules_dict = body.rules.model_dump()
    await launch_session_graph(
        session_id,
        idea=body.idea,
        rules_dict=rules_dict,
        monitoring_cfg=body.rules.monitoring.model_dump(),
    )
    return {"session_id": session_id, "status": "starting"}


RESTARTABLE_STATUSES = frozenset(
    {"interrupted", "stuck", "completed_partial", "failed", "degraded", "waiting_user"}
)


@router.post("/{session_id}/restart")
async def restart_session(session_id: str):
    """Re-launch the agent graph after interrupt, stuck, or empty partial completion."""
    from app.services.session import update_session_status
    from app.services.session_launcher import launch_session_graph
    from app.services.session_runner import session_runner

    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session_runner.is_running(session_id):
        raise HTTPException(409, "Session graph is already running")
    if session["status"] not in RESTARTABLE_STATUSES:
        raise HTTPException(409, f"Cannot restart from status: {session['status']}")

    rules = session.get("rules") or {}
    monitoring_cfg = (rules.get("monitoring") or {})
    await update_session_status(session_id, "running")
    await launch_session_graph(
        session_id,
        idea=session["idea"],
        rules_dict=rules,
        monitoring_cfg=monitoring_cfg,
    )
    await log_bus.emit(
        session_id,
        "log_entry",
        {
            "level": "info",
            "agent_id": "system",
            "message": "Пайплайн перезапущен",
        },
    )
    return {"session_id": session_id, "status": "starting"}


@router.get("/{session_id}")
async def get_session_endpoint(session_id: str):
    from app.services.artifact_store import read_manifest_for_api

    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if not session.get("manifest"):
        disk_manifest = read_manifest_for_api(session_id)
        if disk_manifest:
            session["manifest"] = disk_manifest
    questions = await get_open_questions(session_id)
    return {**session, "open_questions": questions}


@router.get("/{session_id}/health")
async def session_health(session_id: str):
    from app.services.session_runner import session_runner

    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    wd_state = watchdog.get_state(session_id)
    stuck = False
    if wd_state:
        stuck = wd_state.status == "stuck" or wd_state.is_stuck()
    graph_active = session_runner.is_running(session_id)
    return {
        "status": session["status"],
        "stuck": stuck,
        "stuck_since_sec": wd_state.stuck_since_sec() if wd_state else None,
        "recoverable": session["status"] not in ("failed",),
        "current_agent": wd_state.current_agent if wd_state else None,
        "graph_active": graph_active,
    }


@router.post("/{session_id}/answers")
async def submit_answer(session_id: str, body: AnswerRequest):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    await answer_question(session_id, body.question_id, body.answer)
    watchdog.deliver_answer(body.question_id, body.answer)
    return {"status": "answered"}


@router.post("/{session_id}/answers/batch")
async def submit_answers_batch(session_id: str, body: BatchAnswersRequest):
    from app.services.intake import notify_intake_resolved
    from app.services.session import update_session_status

    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    open_qs = await get_open_questions(session_id)
    open_ids = {q["id"] for q in open_qs}
    if not open_ids:
        return {"status": "no_open_questions", "remaining": 0}

    missing = [qid for qid in open_ids if qid not in body.answers]
    if missing:
        raise HTTPException(
            400,
            f"Answer all questions before submitting. Missing: {', '.join(missing[:5])}",
        )

    for qid, answer in body.answers.items():
        if qid not in open_ids:
            continue
        await answer_question(session_id, qid, answer)
        watchdog.deliver_answer(qid, answer)

    notify_intake_resolved(session_id)
    remaining = await get_open_questions(session_id)
    if not remaining:
        await update_session_status(session_id, "running")
        wd = watchdog.get_state(session_id)
        if wd:
            wd.status = "running"
        await log_bus.emit(
            session_id,
            "intake_complete",
            {"ready": True, "answers_count": len(body.answers), "from_user": True},
        )

    return {"status": "answered", "remaining": len(remaining)}


@router.post("/{session_id}/resume")
async def resume_session(session_id: str):
    raise HTTPException(
        501,
        "Resume from checkpoint is not yet supported. Use POST /recover with retry_agent or force_export.",
    )


@router.post("/{session_id}/recover")
async def recover_session(session_id: str, body: RecoverRequest):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    directive: dict = {"action": body.action}
    if body.target_agent:
        directive["target_agent"] = body.target_agent
    if body.max_review_cycles is not None:
        directive["max_review_cycles"] = body.max_review_cycles
    if body.completion_confidence is not None:
        directive["completion_confidence"] = body.completion_confidence
    if body.until_confident is not None:
        directive["until_confident"] = body.until_confident

    if (
        body.max_review_cycles is not None
        or body.completion_confidence is not None
        or body.until_confident is not None
    ):
        set_overrides(session_id, directive)

    enqueue(session_id, directive)

    if body.action == "force_export":
        from app.services.session_runner import session_runner

        session_runner.request_cancel(session_id)

    await log_bus.emit(
        session_id,
        "recovery_started",
        {
            "action": body.action,
            "target_agent": body.target_agent,
        },
    )
    return {"status": "recovery_initiated", "action": body.action, "overrides": get_overrides(session_id)}


@router.get("/{session_id}/control")
async def get_session_control(session_id: str):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    rules = session.get("rules") or {}
    overrides = get_overrides(session_id)
    resilience = rules.get("resilience", {})
    l4 = rules.get("l4", {})
    return {
        "max_review_cycles": overrides.get("max_review_cycles", resilience.get("max_review_cycles", 10)),
        "completion_confidence": overrides.get(
            "completion_confidence", l4.get("completion_confidence", 0.85)
        ),
        "until_confident": overrides.get("until_confident", l4.get("until_confident", True)),
        "overrides_active": bool(overrides),
        "status": session["status"],
        "paused": session["status"] == "paused",
    }


@router.post("/{session_id}/control")
async def session_control(session_id: str, body: SessionControlRequest):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")

    settings = body.model_dump(exclude_none=True)
    action = settings.pop("action", None)

    if settings:
        set_overrides(session_id, {**settings, "action": "update_settings"})
        enqueue(session_id, {"action": "update_settings", **settings})

    if action:
        enqueue(session_id, {"action": action})
        if action == "pause":
            wd = watchdog.get_state(session_id)
            if wd:
                wd.status = "paused"
            from app.services.session import update_session_status

            await update_session_status(session_id, "paused")
        elif action == "resume":
            wd = watchdog.get_state(session_id)
            if wd:
                wd.status = "running"
            from app.services.session import update_session_status

            await update_session_status(session_id, "running")
        elif action == "cancel":
            from app.services.session_runner import session_runner

            session_runner.request_cancel(session_id)
        elif action == "force_export":
            from app.services.session_runner import session_runner

            session_runner.request_cancel(session_id)

    overrides = get_overrides(session_id)
    await log_bus.emit(
        session_id,
        "refinement_settings",
        {
            "action": action,
            **overrides,
        },
    )
    if action:
        await log_bus.emit(
            session_id,
            "recovery_started",
            {"action": action, "target_agent": None},
        )

    return {"status": "ok", "action": action, "overrides": overrides}


@router.get("/{session_id}/artifacts/tasks/{task_path:path}")
async def get_task_artifact(session_id: str, task_path: str):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    try:
        content = read_task_file(session_id, task_path)
    except ValueError:
        raise HTTPException(400, "Invalid task path") from None
    except FileNotFoundError:
        raise HTTPException(404, "Task not found") from None
    return PlainTextResponse(content, media_type="text/markdown")


@router.get("/{session_id}/artifacts/{artifact_type}")
async def get_artifact(session_id: str, artifact_type: str):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    try:
        content, media_type = read_artifact(session_id, artifact_type, session.get("manifest"))
    except FileNotFoundError:
        raise HTTPException(404, f"Artifact not found: {artifact_type}") from None
    return PlainTextResponse(content, media_type=media_type)


@router.get("/{session_id}/tasks")
async def list_tasks(session_id: str):
    output_dir = session_output_dir(session_id) / "tasks"
    if not output_dir.exists():
        return {"tasks": []}
    tasks = []
    for f in sorted(output_dir.rglob("*.md")):
        tasks.append({"path": str(f.relative_to(output_dir)), "name": f.name})
    return {"tasks": tasks}


@router.get("/{session_id}/logs")
async def get_logs(session_id: str, from_seq: int = 0, limit: int = 500):
    logs = await log_bus.get_log_history(session_id, from_seq=from_seq, limit=min(limit, 1000))
    return {"logs": logs, "count": len(logs)}


@router.get("/{session_id}/export")
async def export_session(session_id: str):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    zip_bytes = build_zip(session_id)
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="pink-spec-{session_id[:8]}.zip"'},
    )
