"""Project admin REST routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.services.output_migration import migrate_output_folders
from app.services.projects import delete_project, get_project, list_projects

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


@router.get("")
async def list_projects_endpoint(
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    projects, total = await list_projects(limit=limit, offset=offset)
    return {"projects": projects, "total": total, "limit": limit, "offset": offset}


@router.get("/{session_id}")
async def get_project_endpoint(session_id: str):
    project = await get_project(session_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    return project


@router.delete("/{session_id}")
async def delete_project_endpoint(session_id: str):
    result = await delete_project(session_id)
    if result.get("error") == "not_found":
        raise HTTPException(404, "Project not found")
    if result.get("error") == "already_deleted":
        raise HTTPException(410, "Project already archived")
    if result.get("error") == "active_session":
        raise HTTPException(409, "Cannot delete active session — wait until it finishes or cancel")
    return result


@router.post("/migrate-output")
async def migrate_output_endpoint():
    stats = await migrate_output_folders()
    return {"status": "ok", **stats}
