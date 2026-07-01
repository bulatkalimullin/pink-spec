"""Document ingestion pipeline: load → chunk → embed → store."""
from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

ALLOWED_EXTENSIONS = {".md", ".txt", ".pdf"}
MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB


def load_file(path: Path) -> str:
    if path.suffix not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Unsupported file type: {path.suffix}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise ValueError(f"File too large: {path.name}")
    if path.suffix == ".pdf":
        try:
            import pypdf

            reader = pypdf.PdfReader(str(path))
            return "\n".join(page.extract_text() or "" for page in reader.pages)
        except ImportError:
            raise RuntimeError("pypdf not installed; cannot ingest PDF")
    return path.read_text(encoding="utf-8", errors="ignore")


def chunk_text(text: str, chunk_size: int = 800, overlap: int = 100) -> list[str]:
    """Simple recursive character splitter."""
    separators = ["\n\n", "\n", ". ", " ", ""]
    return _split(text, chunk_size, overlap, separators)


def _split(text: str, chunk_size: int, overlap: int, separators: list[str]) -> list[str]:
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    sep = ""
    for s in separators:
        if s in text:
            sep = s
            break
    parts = text.split(sep) if sep else [text[i : i + chunk_size] for i in range(0, len(text), chunk_size)]
    chunks: list[str] = []
    current = ""
    for part in parts:
        candidate = (current + sep + part).strip()
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                chunks.append(current)
            # carry overlap
            current = current[-overlap:] + sep + part if current else part
    if current.strip():
        chunks.append(current.strip())
    return [c for c in chunks if c.strip()]


async def ingest_sources(sources: list[str], retriever, session_id: str) -> dict[str, Any]:
    """Ingest documents from list of paths/dirs. Returns {files_ok, files_failed, chunks}."""
    from app.services.log_bus import log_bus

    files_ok = 0
    files_failed = 0
    total_chunks = 0

    for source in sources:
        path = Path(source)
        candidates = list(path.rglob("*")) if path.is_dir() else [path]
        for file_path in candidates:
            if file_path.suffix not in ALLOWED_EXTENSIONS:
                continue
            try:
                text = load_file(file_path)
                chunks = chunk_text(text)
                metadatas = [{"source": str(file_path), "chunk": i} for i in range(len(chunks))]
                await retriever.add_texts(chunks, metadatas)
                total_chunks += len(chunks)
                files_ok += 1
                await log_bus.emit(
                    session_id,
                    "log_entry",
                    {"level": "info", "agent_id": "rag", "message": f"Ingested {file_path.name} ({len(chunks)} chunks)"},
                )
            except Exception as e:
                files_failed += 1
                logger.warning("ingest_failed", file=str(file_path), error=str(e))
                await log_bus.emit(
                    session_id,
                    "log_entry",
                    {"level": "warn", "agent_id": "rag", "message": f"Skip {file_path.name}: {e}"},
                )

    return {"files_ok": files_ok, "files_failed": files_failed, "chunks": total_chunks}
