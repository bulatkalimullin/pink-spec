"""RAG document ingestion endpoint."""
from __future__ import annotations

import tempfile
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter(prefix="/api/v1/rag", tags=["rag"])

ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf"}
MAX_FILE_SIZE = 10 * 1024 * 1024


@router.post("/ingest")
async def ingest_document(session_id: str, file: UploadFile = File(...)):
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"File type not allowed: {suffix}")

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(413, "File too large (max 10MB)")

    # Write to temp file and ingest
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        from app.llm.hf_provider import build_embedding_provider
        from app.rag.retriever import ChromaRetriever, BM25Retriever
        from app.rag.ingest import ingest_sources

        # Try to get embedding provider from app state
        try:
            from app.main import embedding_provider  # type: ignore
            retriever = ChromaRetriever(session_id=session_id, embedding_provider=embedding_provider)
        except Exception:
            retriever = BM25Retriever()

        result = await ingest_sources([str(tmp_path)], retriever, session_id)
        return {"status": "ok", **result}
    finally:
        tmp_path.unlink(missing_ok=True)
