"""Session REST routes."""
from __future__ import annotations

import asyncio
from typing import Annotated

import structlog
from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import PlainTextResponse, Response

from app.schemas.rules import StartSessionRequest, AnswerRequest, RecoverRequest
from app.services.session import (
    create_session,
    get_session,
    get_open_questions,
    answer_question,
    get_latest_checkpoint,
)
from app.services.log_bus import log_bus
from app.services.export import build_zip, read_artifact, read_task_file, session_output_dir
from app.services.session_watchdog import watchdog

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/api/v1/sessions", tags=["sessions"])


def _get_providers():
    """Lazy import to avoid circular at startup."""
    from app.main import llm_provider, embedding_provider  # type: ignore
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
async def start_session(session_id: str, body: StartSessionRequest, background_tasks: BackgroundTasks):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    if session["status"] not in ("pending", "failed"):
        raise HTTPException(409, f"Session already in state: {session['status']}")

    llm, emb = _get_providers()

    async def _run():
        from app.agent.graph import run_graph
        monitoring_cfg = body.rules.monitoring.model_dump()
        from app.services.system_monitor import system_monitor
        system_monitor.add_session(session_id, monitoring_cfg)
        try:
            await run_graph(
                session_id=session_id,
                idea=body.idea,
                rules=body.rules.model_dump(),
                llm_provider=llm,
                embedding_provider=emb,
            )
        finally:
            system_monitor.remove_session(session_id)

    background_tasks.add_task(_run)
    return {"session_id": session_id, "status": "starting"}


@router.get("/{session_id}")
async def get_session_endpoint(session_id: str):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    questions = await get_open_questions(session_id)
    return {**session, "open_questions": questions}


@router.get("/{session_id}/health")
async def session_health(session_id: str):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    wd_state = watchdog.get_state(session_id)
    return {
        "status": session["status"],
        "stuck": wd_state.is_stuck() if wd_state else False,
        "recoverable": session["status"] not in ("failed",),
        "current_agent": wd_state.current_agent if wd_state else None,
    }


@router.post("/{session_id}/answers")
async def submit_answer(session_id: str, body: AnswerRequest):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    await answer_question(session_id, body.question_id, body.answer)
    watchdog.deliver_answer(body.question_id, body.answer)
    return {"status": "answered"}


@router.post("/{session_id}/resume")
async def resume_session(session_id: str):
    checkpoint = await get_latest_checkpoint(session_id)
    if not checkpoint:
        raise HTTPException(404, "No checkpoint found")
    await log_bus.emit(session_id, "recovery_started", {
        "action": "resume_from_checkpoint",
        "target_agent": checkpoint.get("agent_id"),
    })
    return {"checkpoint_id": checkpoint["id"], "agent_id": checkpoint.get("agent_id")}


@router.post("/{session_id}/recover")
async def recover_session(session_id: str, body: RecoverRequest):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    await log_bus.emit(session_id, "recovery_started", {
        "action": body.action,
        "target_agent": body.target_agent,
    })
    return {"status": "recovery_initiated", "action": body.action}


@router.get("/{session_id}/artifacts/tasks/{task_path:path}")
async def get_task_artifact(session_id: str, task_path: str):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    try:
        content = read_task_file(session_id, task_path)
    except ValueError:
        raise HTTPException(400, "Invalid task path")
    except FileNotFoundError:
        raise HTTPException(404, "Task not found")
    return PlainTextResponse(content, media_type="text/markdown")


@router.get("/{session_id}/artifacts/{artifact_type}")
async def get_artifact(session_id: str, artifact_type: str):
    session = await get_session(session_id)
    if not session:
        raise HTTPException(404, "Session not found")
    try:
        content, media_type = read_artifact(
            session_id, artifact_type, session.get("manifest")
        )
    except FileNotFoundError:
        raise HTTPException(404, f"Artifact not found: {artifact_type}")
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
