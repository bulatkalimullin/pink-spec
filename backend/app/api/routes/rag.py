"""RAG document ingestion — queues ingest job on agent-worker via Kafka."""

from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import get_settings
from app.services.kafka_commands import publish_rag_ingest

router = APIRouter(prefix="/api/v1/rag", tags=["rag"])

ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf"}
MAX_FILE_SIZE = 10 * 1024 * 1024


@router.post("/ingest", status_code=202)
async def ingest_document(session_id: str, file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type not allowed: {suffix}")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, "File too large (max 10MB)")

    settings = get_settings()
    ingest_dir = Path(settings.vector_path) / "ingest_queue" / session_id
    ingest_dir.mkdir(parents=True, exist_ok=True)
    dest = ingest_dir / f"{uuid.uuid4().hex}{suffix}"
    dest.write_bytes(content)

    await publish_rag_ingest(
        session_id,
        temp_paths=[str(dest)],
        sources_meta=[{"filename": file.filename, "size": len(content)}],
    )
    return {"status": "queued", "path": str(dest)}
