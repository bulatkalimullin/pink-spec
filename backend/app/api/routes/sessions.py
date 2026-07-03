"""Session REST routes."""

from __future__ import annotations

import structlog
from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, Response

from app.schemas.rules import (
    AnswerRequest,
    BatchAnswersRequest,
    RecoverRequest,
    SessionControlRequest,
    StartSessionRequest,
)
from app.services.export import build_zip, read_artifact, read_task_file, session_output_dir
from app.services.kafka_commands import (
    publish_cancel,
    publish_control,
    publish_intake_answers_ready,
    publish_restart,
    publish_start,
)
from app.services.log_bus import log_bus
from app.services.session import (
    answer_question,
    create_session,
    get_latest_checkpoint,
    get_open_questions,
    get_session,
    is_worker_active,
    update_session_status,
)
from app.services.session_control import get_overrides, set_overrides

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


@router.post("", status_code=201)
async def create_session_endpoint(body: StartSessionRequest):
    rules_dict = body.rules.model_dump()
    session_id = await create_session(
        spec_level=body.rules.spec_level.value,
        idea=body.idea,
        rules=rules_dict,
    )
    return {"session_id": session_id, "spec_level": body.rules.spec_level}


@router.post("/{session_id}/start", status_code=202)
async def start_session(session_id: str, body: StartSessionRequest):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session["status"] not in ("pending", "failed"):
        raise HTTPException(409, f"Session already in state: {session['status']}")
    if await is_worker_active(session_id):
        raise HTTPException(409, "Session is already queued or running on worker")

    rules_dict = body.rules.model_dump()
    await update_session_status(session_id, "queued")
    await publish_start(
        session_id,
        idea=body.idea,
        rules=rules_dict,
        monitoring=body.rules.monitoring.model_dump(),
    )
    return {"session_id": session_id, "status": "queued"}


RESTARTABLE_STATUSES = frozenset(
    {"interrupted", "stuck", "completed_partial", "failed", "degraded", "waiting_user"}
)


@router.post("/{session_id}/restart", status_code=202)
async def restart_session(session_id: str):
    """Re-queue session on agent-worker after interrupt or partial completion."""
    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if await is_worker_active(session_id):
        raise HTTPException(409, "Session is already queued or running on worker")
    if session["status"] not in RESTARTABLE_STATUSES:
        raise HTTPException(409, f"Cannot restart from status: {session['status']}")

    rules = session.get("rules") or {}
    monitoring_cfg = rules.get("monitoring") or {}
    await update_session_status(session_id, "queued")
    await publish_restart(
        session_id,
        idea=session["idea"],
        rules=rules,
        monitoring=monitoring_cfg,
    )
    await log_bus.emit(
        session_id,
        "log_entry",
        {
            "level": "info",
            "agent_id": "system",
            "message": "Пайплайн поставлен в очередь на перезапуск",
        },
    )
    return {"session_id": session_id, "status": "queued"}


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
    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    graph_active = await is_worker_active(session_id)
    return {
        "status": session["status"],
        "stuck": session["status"] == "stuck",
        "stuck_since_sec": None,
        "recoverable": session["status"] not in ("failed",),
        "current_agent": None,
        "graph_active": graph_active,
        "worker_heartbeat_at": session.get("worker_heartbeat_at"),
    }


@router.post("/{session_id}/answers")
async def submit_answer(session_id: str, body: AnswerRequest):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    await answer_question(session_id, body.question_id, body.answer)
    return {"status": "answered"}


@router.post("/{session_id}/answers/batch")
async def submit_answers_batch(session_id: str, body: BatchAnswersRequest):
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

    await publish_intake_answers_ready(session_id, len(body.answers))
    remaining = await get_open_questions(session_id)
    if not remaining:
        await update_session_status(session_id, "running")
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

    await publish_control(session_id, directive)

    if body.action == "force_export":
        await publish_cancel(session_id)

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
        await publish_control(session_id, {"action": "update_settings", **settings})

    if action:
        await publish_control(session_id, {"action": action})
        if action == "pause":
            await update_session_status(session_id, "paused")
        elif action == "resume":
            await update_session_status(session_id, "running")
        elif action in ("cancel", "force_export"):
            await publish_cancel(session_id)

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
